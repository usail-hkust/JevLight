"""Pinned author decision runtimes with independent, complete request batches.

The adapters retain each author's tokenizer, readout and calibration. Batch
capacity and memory-margin probing are supplied by the common step runtime.
"""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import sys
from types import ModuleType


def author_module(directory, module):
    """Namespace each frozen package so two checkpoints cannot share stale code."""
    directory = Path(directory).resolve()
    name = '_decision_author_' + hashlib.sha256(str(directory).encode()).hexdigest()[:16]
    if name not in sys.modules:
        package = ModuleType(name)
        package.__path__ = [str(directory)]
        sys.modules[name] = package
    return importlib.import_module(name + '.' + module)


def validate_mapping(request, result):
    """Validate schema and candidate mapping, without probability acceptance."""
    answers = result.get('answers', {})
    if set(answers) != set(request['questions']):
        raise ValueError('Author response lost question IDs')
    for qid, question in request['questions'].items():
        answer = answers[qid]
        if 'error' in answer:
            raise ValueError(f"{qid}: {answer['error']}: {answer.get('message', '')}")
        if answer.get('type') != question['type']:
            raise ValueError(f'{qid}: author answer type changed')
        if question['type'] == 'choice':
            if answer.get('choice') not in question['criteria']:
                raise ValueError(f'{qid}: invalid phase candidate')
            if list(answer.get('probabilities', {})) != list(question['criteria']):
                raise ValueError(f'{qid}: candidate mapping or order changed')
    return result


def text_request(request):
    if request.get('images') or request.get('videos'):
        raise ValueError('This adapter qualifies complete text/JSON requests only')
    return request


def context_limit(config, weights):
    native = json.loads((weights / 'config.json').read_text())
    supported = native.get('text_config', native)['max_position_embeddings']
    maximum = config['max_length']
    if type(maximum) is not int or not 0 < maximum <= supported:
        raise ValueError('Context budget exceeds the published backbone capability')
    return maximum


class D3Native:
    def __init__(self, config):
        weights = Path(config['weights_path']).resolve()
        self.module = author_module(weights, 'd3_runtime')
        self.max_length = context_limit(config, weights)
        self.engine = self.module.D3.from_pretrained(
            weights, device='cuda:0', local_files_only=True, verify='fast',
            max_length=self.max_length, model_name=config['model_id'])
        # Noncausal D3 calls decoder layers directly, bypassing backbone.forward.
        self.batch_probe_module = self.engine.backbone.language_model.layers[0]

    @classmethod
    def for_encoding(cls, config):
        from transformers import AutoTokenizer
        self = cls.__new__(cls)
        weights = Path(config['weights_path']).resolve()
        self.module = author_module(weights, 'd3_runtime')
        self.max_length = context_limit(config, weights)
        native = json.loads((weights / 'decision_config.json').read_text())
        engine = self.module.D3.__new__(self.module.D3)
        engine.tokenizer = AutoTokenizer.from_pretrained(str(weights), local_files_only=True)
        engine.tokenizer.padding_side = 'left'
        engine.prompt = native['prompt']
        engine.codes, engine.token_ids = self.module.answer_codes(engine.tokenizer)
        if engine.codes != native['codes'] or engine.token_ids != native['token_ids']:
            raise ValueError('Author answer-code identity differs from tokenizer')
        engine.max_length = self.max_length
        engine.permutation_average = False
        self.engine = engine
        self.audit_tokenizer_path = str(weights)
        return self

    def prepared(self, request):
        text_request(request)
        prepared = self.engine.prepare(request['state'], request['questions'])
        if prepared.errors:
            raise ValueError(json.dumps(prepared.errors, ensure_ascii=False))
        if prepared.keys != list(request['questions']) or prepared.runnable != prepared.keys:
            raise ValueError('Author encoder lost or reordered questions')
        if any(prepared.questions[k].keys != list(q['criteria'])
               for k, q in request['questions'].items() if q['type'] == 'choice'):
            raise ValueError('Author encoder changed candidate mapping')
        return prepared

    def encode(self, request):
        prepared = self.prepared(request)
        return [dict(question_id=key, encoded_tokens=len(prepared.sequences[key]),
                     max_length=self.max_length, truncated=False)
                for key in prepared.keys]

    def native(self, request):
        self.prepared(request)
        return validate_mapping(request, self.engine.system_one(**request))

    def native_batch(self, requests, batch_size):
        if type(batch_size) is not int or batch_size < 1:
            raise ValueError('batch_size must be a positive integer')
        requests = list(requests)
        if len(requests) > batch_size:
            raise ValueError('Use the step capacity adapter to split request groups')
        if not requests:
            return []
        prepared = [self.prepared(request) for request in requests]
        rows = [(i, key) for i, item in enumerate(prepared) for key in item.keys]
        sequences = [prepared[i].sequences[key] for i, key in rows]
        counts = [len(prepared[i].questions[key].keys) for i, key in rows]
        # One native GPU call for all question rows, never one call per junction.
        probabilities = self.engine.probabilities(sequences, counts)
        if len(probabilities) != len(rows):
            raise ValueError('Author batch returned an incomplete row mapping')
        grouped = [{} for _ in requests]
        for (index, key), values in zip(rows, probabilities, strict=True):
            grouped[index][key] = values
        return [validate_mapping(request, self.engine.respond(item, values,
                    sum(len(s) for s in item.sequences.values())))
                for request, item, values in zip(requests, prepared, grouped, strict=True)]


class PplxDeciderNative:
    def __init__(self, config):
        weights = Path(config['weights_path']).resolve()
        self.module = author_module(weights / 'source/src/pplx_decider', 'model')
        self.max_length = context_limit(config, weights)
        self.engine = self.module.Decider.from_pretrained(
            weights, device='cuda:0', max_length=self.max_length, fast=False,
            cpu_threads=int(config.get('cpu_threads', 1)))
        self.batch_probe_module = self.engine.backbone
        self.packed = None
        backend = config.get('batch_backend', 'author')
        if backend == 'author_packed':
            fast = author_module(weights / 'source/src/pplx_decider', 'fast')
            # Keep the scalar reference untouched; no FP8 or model compilation.
            self.packed = fast.FastPath(self.engine, self.module.FastOptions(
                compile=None, cuda_graphs=False, fp8=False, prefetch=False))
        elif backend != 'author':
            raise ValueError(f'Unknown author batch backend: {backend}')

    @classmethod
    def for_encoding(cls, config):
        from transformers import AutoProcessor
        self = cls.__new__(cls)
        weights = Path(config['weights_path']).resolve()
        protocol = author_module(weights / 'source/src/pplx_decider', 'protocol')
        from types import SimpleNamespace
        processor = AutoProcessor.from_pretrained(str(weights), local_files_only=True)
        processor.tokenizer.padding_side = 'left'
        native = json.loads((weights / 'decision_config.json').read_text())
        if json.loads((weights / 'joint_config.json').read_text()) != protocol.PROTOCOL:
            raise ValueError('Unexpected author joint protocol')
        if [processor.tokenizer.encode(c, add_special_tokens=False) for c in native['codes']] != [[t] for t in native['token_ids']]:
            raise ValueError('Author answer-code identity differs from tokenizer')
        self.engine = SimpleNamespace(encoder=protocol.Encoder(processor, native['codes']))
        self.max_length = context_limit(config, weights)
        self.audit_tokenizer_path = str(weights)
        return self

    def prepared(self, request):
        text_request(request)
        encoder = self.engine.encoder
        encoder.validate(request)
        chunk = encoder.encode(request)
        # All questions retain one independent state sequence. Never silently
        # split a joint request or combine distinct junctions into one state.
        if chunk.length > self.max_length:
            raise ValueError(f'Complete joint request needs {chunk.length} tokens, limit {self.max_length}')
        if list(chunk.keys) != list(request['questions']):
            raise ValueError('Author joint encoder lost question IDs')
        return chunk

    def encode(self, request):
        chunk = self.prepared(request)
        return [dict(question_id=key, encoded_tokens=chunk.length,
                     readout_position=int(position), max_length=self.max_length,
                     truncated=False)
                for key, position in zip(chunk.keys, chunk.markers, strict=True)]

    def native(self, request):
        self.prepared(request)
        return validate_mapping(request, self.engine.decide(request))

    def native_batch(self, requests, batch_size):
        if type(batch_size) is not int or batch_size < 1:
            raise ValueError('batch_size must be a positive integer')
        requests = list(requests)
        if len(requests) > batch_size:
            raise ValueError('Use the step capacity adapter to split request groups')
        if not requests:
            return []
        chunks = [self.prepared(request) for request in requests]
        self.last_engine_forward_rows = []
        # The readout hook proves completion on CUDA. For a packed forward,
        # logical rows are the independent sequences in the author's cu_seqlens.
        def completed(module, args, output):
            import torch
            if not torch.is_tensor(output) or not output.is_cuda:
                raise RuntimeError('Author readout did not execute on CUDA')
            if output.shape[0] != sum(len(c.keys) for c in chunks):
                raise ValueError('Author GPU readout marker count mismatch')
            if self.packed is not None:
                fast = sys.modules[type(self.packed).__module__]
                boundaries = fast._PACK['cu_cpu'].tolist()
                lengths = [b-a for a,b in zip(boundaries, boundaries[1:])]
                if lengths != [c.length for c in chunks]:
                    raise ValueError('Packed GPU sequence boundaries differ from complete inputs')
            self.last_engine_forward_rows.append(len(chunks))
        handle = self.engine.readout.register_forward_hook(completed)
        try:
            # No default 32k token budget: try the whole step; the shared
            # capacity manager lowers request count only after measured failure.
            values = (self.packed.forward(chunks) if self.packed is not None
                      else self.engine.reference_logits(chunks))
        finally:
            handle.remove()
        if len(values) != len(chunks) or not self.last_engine_forward_rows:
            raise ValueError('Incomplete author GPU batch')
        return [validate_mapping(request, self.engine._respond(request,
                    dict(zip(chunk.keys, rows, strict=True)), [chunk], self.engine.temperature))
                for request, chunk, rows in zip(requests, chunks, values, strict=True)]
