"""Valen-Decision-1.5: frozen shared-state compiler, block-attention engine and FP32 Mixer head."""
import importlib
import json
import sys
from types import ModuleType
from jevlight.backends.pooled_native_runtime import PoolingNativeBase,ROOT
from jevlight.backends.valen_decision15_blocks import compiled_segments,glue_tokens,prompt_segments

PACKAGE='_jevlight_frozen_valen_decision15'


def native_module(source,name):
    # A package of its own: the Valen 1.0 frozen sources are never shadowed.
    if PACKAGE not in sys.modules:
        module=ModuleType(PACKAGE);module.__path__=[str(source)];sys.modules[PACKAGE]=module
    return importlib.import_module(PACKAGE+'.'+name)


class TextProcessor:
    """The frozen processor's text-only chat-template path; no media is admitted."""
    def __init__(self,tokenizer):self.tokenizer=tokenizer

    def apply_chat_template(self,messages,**kwargs):
        for message in messages:
            if not isinstance(message['content'],str)and any(part['type']!='text'for part in message['content']):
                raise ValueError('The qualified benchmark uses complete text-only inputs')
        kwargs.pop('processor_kwargs',None)
        return self.tokenizer.apply_chat_template(messages,**kwargs)


def published_config(source):
    published=json.loads((source/'config.json').read_text())
    if (published.get('valen_decision_version')!='1.5'or published.get('valen_full_attention_mask')!='bbox_blocks'
            or published.get('qwen_execution')!='shared_state'):
        raise ValueError('Checkpoint is not a Valen-Decision-1.5 shared-state release')
    return published


def native_tokenizer(source):
    from transformers import AutoTokenizer,PreTrainedTokenizerFast
    tokenizer_config=json.loads((source/'tokenizer_config.json').read_text())
    return (PreTrainedTokenizerFast.from_pretrained(source,local_files_only=True)
            if tokenizer_config.get('tokenizer_class')=='TokenizersBackend'
            else AutoTokenizer.from_pretrained(source,local_files_only=True))


def native_compiler(config):
    source=ROOT/config['weights_path'];published=published_config(source)
    if config['max_length']>published['valen_max_length']:
        raise ValueError('Serving limit exceeds the published native compiler limit')
    processor=TextProcessor(native_tokenizer(source))
    return native_module(source,'compiler').Compiler(processor,max_length=config['max_length'],
        media_kwargs=published.get('valen_media_kwargs',{}),execution='shared_state')


def compile_request(compiler,request,glue):
    state=request['state']
    if (isinstance(state,dict)and set(state)=={'messages'})or any(
            isinstance(q,dict)and q.get('type')=='bbox'for q in request['questions'].values()):
        raise ValueError('Image states and bbox questions need the author inference engine')
    state=compiler.compile(dict(request=dict(state=json.dumps(request['state'],ensure_ascii=False),questions=request['questions'])))
    if state.inputs is None or state.media:raise ValueError('Complete native text-only shared-state encoding required')
    for question in state.questions:
        if question.kind!='choice'or question.keys!=list(request['questions'][question.qid]['criteria'])or len(question.branches)!=1:
            raise ValueError('Native phase question/candidate mapping differs')
    ids=state.inputs['input_ids'][0].tolist()
    # The engine sees token ids only. Its block ids must equal the compiler's
    # for every token, otherwise the trained mask would not be the one applied.
    if prompt_segments(ids,glue)!=compiled_segments(state):
        raise ValueError('Engine block boundaries differ from the native compiler segments')
    return state,ids


class ValenDecision15PoolingNative(PoolingNativeBase):
    def pooling_registration(self):
        from jevlight.backends.native_pooling_registry import (
            VALEN_DECISION15_ARCHITECTURES,VALEN_DECISION15_WORKER,
            register_valen_decision15_pooling_models)
        return VALEN_DECISION15_ARCHITECTURES,VALEN_DECISION15_WORKER,register_valen_decision15_pooling_models

    def __init__(self,config):
        import torch
        from safetensors import safe_open
        source=ROOT/config['weights_path'];published=published_config(source)
        self.compiler=native_compiler(config);self.responses=native_module(source,'responses')
        self.glue=glue_tokens(self.compiler.tokenizer)
        head=native_module(source,'heads').build_head(published['text_config']['hidden_size'],published['valen_head']).float().eval()
        index=source/'model.safetensors.index.json'
        shards=(sorted({v for n,v in json.loads(index.read_text())['weight_map'].items()if n.startswith('head.')})
                if index.exists()else['model.safetensors'])
        state={}
        for shard in shards:
            with safe_open(source/shard,framework='pt',device='cpu')as archive:
                for name in archive.keys():
                    if name.startswith('head.'):
                        value=archive.get_tensor(name)
                        if value.dtype!=torch.float32:raise ValueError('The released Mixer precision changed')
                        state[name.removeprefix('head.')]=value
        head.load_state_dict(state,strict=True);self.released_head_tensors_verified=len(state)
        # Block forwards neither read nor write the KV cache: every prompt must be
        # one complete prefill, never split across scheduler steps.
        self.initialize_engine(config,source,architecture='ValenDecision15MarkerEngine',enable_chunked_prefill=False)
        self.model.head=head.to('cuda').eval()

    def _compile(self,request):
        state,ids=compile_request(self.compiler,request,self.glue)
        if state.logical_tokens>self.max_length:raise ValueError('Complete native input exceeds the engine window')
        return state,ids

    def encode(self,request):
        state,_=self._compile(request)
        return [dict(logical_tokens=state.logical_tokens,compute_tokens=state.compute_tokens,
                     max_length=self.max_length,truncated=False)]

    def native_batch(self,requests,batch_size):
        import torch
        from jevlight.backends.decision_model_service import validate_answers
        compiled=[self._compile(r)for r in requests]
        states=[state for state,_ in compiled];rows=[ids for _,ids in compiled]
        with torch.inference_mode():
            # Reset the engine's row counts (profiling, an earlier failed attempt), then
            # require every row of this pool to have run under the block mask.
            self.engine.collective_rpc('valen_decision15_block_rows')
            values=self.pool(rows);results=[]
            reports=self.engine.collective_rpc('valen_decision15_block_rows')
            if any(report['block_rows']!=len(rows)or report['causal_rows']for report in reports):
                raise ValueError('The engine did not apply the block mask to every native row')
            for request,state,ids,value in zip(requests,states,rows,values,strict=True):
                hidden=torch.as_tensor(value.outputs.data)
                if hidden.ndim!=2 or hidden.shape[0]!=len(ids):raise ValueError('The engine omitted native token states')
                answers={}
                for question in state.questions:
                    features=self.model.head.extract_features(hidden.unsqueeze(0),question.branches[0]).to('cuda')
                    logits=self.model.head.score_features(features)
                    answers[question.qid]=self.responses.answer(question,logits,1.)
                result=dict(model=self.config['model_id'],answers=answers,
                    usage=dict(input_tokens=state.logical_tokens,output_tokens=0),
                    internal_usage=dict(compute_tokens=state.compute_tokens))
                results.append(validate_answers(request,result))
        return results
