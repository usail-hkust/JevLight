"""Shared guarded GPU pooling and progress for native decision runtimes."""
import os
from pathlib import Path
import uuid

ROOT=Path(__file__).resolve().parents[2]


class PoolingNativeBase:
    emits_gpu_chunk_progress=True

    def initialize_engine(self,config,source,*,task='token_embed',architecture='NativeMarkerEngine',**options):
        import torch
        from jevlight.backends.cuda_runtime import prepare_cuda_device, configure_cpu_threads
        prepare_cuda_device()
        configure_cpu_threads(default=8)
        os.environ['VLLM_ENABLE_V1_MULTIPROCESSING']='0'
        if options.get('enable_lora'):
            from jevlight.backends.vllm_lora import install_fp32_lora_linear
            install_fp32_lora_linear()
        from vllm import LLM
        from vllm.config import PoolerConfig
        from jevlight.backends.native_pooling_registry import (
            NATIVE_POOLING_ARCHITECTURES, NATIVE_POOLING_WORKER,
            register_native_pooling_models)
        if architecture not in NATIVE_POOLING_ARCHITECTURES:
            raise ValueError('Unqualified native pooling architecture')
        parallel_size=config.get('engine_tensor_parallel_size',1)
        if type(parallel_size) is not int or parallel_size < 1:
            raise ValueError('Native tensor parallel size must be a positive integer')
        if parallel_size > 1:
            if config.get('native_pooling_tp_qualification') is not True:
                raise ValueError('Native tensor parallelism requires explicit qualification mode')
            if options.get('enable_lora'):
                raise ValueError('Sharded native adapter verification is not qualified')
            if torch.cuda.device_count() != parallel_size:
                raise ValueError('Qualification requires exactly the selected worker devices')
            options['distributed_executor_backend']='mp'
        expected_uuids=[str(torch.cuda.get_device_properties(i).uuid) for i in range(parallel_size)]
        if len(set(expected_uuids)) != parallel_size:
            raise ValueError('Native workers require distinct device identities')
        register_native_pooling_models()
        self.config=config;self.source=Path(source);self.task=task
        self.max_length=int(config.get('engine_max_length',config['max_length']))
        if self.max_length>config['max_length']:raise ValueError('Engine window exceeds the model window')
        pooler=(PoolerConfig(seq_pooling_type='LAST',use_activation=False)if task=='embed'
                else PoolerConfig(task=task,tok_pooling_type='ALL',use_activation=False))
        self.engine=LLM(model=str(source),runner='pooling',convert='embed',
            hf_overrides={'architectures':[architecture]},pooler_config=pooler,skip_tokenizer_init=True,
            dtype='bfloat16',tensor_parallel_size=parallel_size,worker_cls=NATIVE_POOLING_WORKER,max_model_len=self.max_length,
            max_num_seqs=int(config.get('engine_max_sequences',196)),max_num_batched_tokens=int(config['engine_token_budget']),
            gpu_memory_utilization=float(config.get('engine_gpu_memory_utilization',.85)),
            enable_prefix_caching=False,enforce_eager=True,**options)
        # Keep only author readout heads in the service. The engine backbone
        # belongs to its worker and may not exist in this process.
        self.model=torch.nn.Module()
        self.last_engine_forward_rows=[];self.engine_forward_evidence=[]
        # Multi-worker execution is opt-in for qualification, never a default.
        self.expected_worker_uuids=expected_uuids
        self.worker_evidence_dir=(ROOT/'results/native_pooling'/uuid.uuid4().hex).resolve()
        self.worker_evidence_dir.mkdir(parents=True,exist_ok=False)

    def verify_lev_adapter(self, source):
        # The current exact-tensor verifier qualifies unsharded adapters only.
        # Do not silently apply it to a TP shard or trust driver-local weights.
        if len(self.expected_worker_uuids) != 1:
            raise ValueError('Sharded native adapter verification is not qualified')
        reports=self.engine.collective_rpc('verify_lev_adapter',args=(str(source),))
        if (len(reports)!=1 or reports[0].get('rank')!=0
                or type(reports[0].get('tensor_count')) is not int
                or reports[0]['tensor_count']<=0):
            raise ValueError('Incomplete worker native adapter verification')
        return reports[0]['tensor_count']

    def pool(self,rows,*,lora=None):
        from vllm import PoolingParams
        if any(not ids or len(ids)>self.max_length for ids in rows):
            raise ValueError('Complete native tokens exceed the verified engine window')
        self.last_engine_forward_rows.clear();self.engine_forward_evidence.clear()
        self.last_worker_memory=[]
        from jevlight.backends.native_pooling_evidence import WorkerEvidence
        step_id=uuid.uuid4().hex
        self.last_worker_step_id=step_id
        evidence=None
        error=None
        started=False
        # Cleanup also runs for validation/encode failures. Never replace the
        # original engine error with a secondary evidence/cleanup failure.
        try:
            armed=self.engine.collective_rpc('begin_native_step',args=(step_id,str(self.worker_evidence_dir)))
            evidence=WorkerEvidence(armed,self.expected_worker_uuids,step_id,self.worker_evidence_dir,
                notify=getattr(getattr(self,'_step_progress',None),'notify',None))
            evidence.start();started=True
            values=self.engine.encode([dict(prompt_token_ids=ids)for ids in rows],
                PoolingParams(task=self.task,use_activation=False),pooling_task=self.task,lora_request=lora,use_tqdm=False)
        except BaseException as failure:
            error=failure
            raise
        finally:
            cleanup_errors=[]
            if started:
                try:evidence.stop()
                except BaseException as failure:cleanup_errors.append(failure)
            try:
                reports=self.engine.collective_rpc('finish_native_step',args=(step_id,))
                self.last_worker_reports=reports
                if evidence is not None and not cleanup_errors:evidence.finish(reports)
            except BaseException as failure:cleanup_errors.append(failure)
            if evidence is not None:
                self.last_worker_memory=evidence.memory_summary()
                self.last_engine_forward_rows[:]=[chunk[0]['rows'] for chunk in evidence.completed]
                self.engine_forward_evidence[:]=[event for chunk in evidence.completed for event in chunk]
            if cleanup_errors:
                if error is not None:
                    for failure in cleanup_errors:error.add_note(f'Worker evidence cleanup: {failure!r}')
                else:
                    raise cleanup_errors[0]
        if len(values)!=len(rows)or any(value.prompt_token_ids!=ids for value,ids in zip(values,rows,strict=True)):
            raise ValueError('The engine omitted tokens or changed native row mapping')
        if not self.last_engine_forward_rows:raise ValueError('No actual GPU execution')
        return values

    def native(self,request):
        return self.native_batch([request],1)[0]
