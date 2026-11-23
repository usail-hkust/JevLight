"""Text backbone pooling for frozen native marker decision heads."""
from jevlight.backends.vllm_decision_models import OpenJevEngineForEmbedding


class NativeMarkerEngine(OpenJevEngineForEmbedding):
    def load_weights(self, weights):
        def mapped():
            for name, value in weights:
                if name.startswith('model.language_model.'):
                    name = 'model.' + name.removeprefix('model.language_model.')
                elif name.startswith(('layers.', 'embed_tokens.', 'norm.')):
                    name = 'model.' + name
                if name.startswith(('model.layers.', 'model.embed_tokens.', 'model.norm.')):
                    yield name, value
        return super(OpenJevEngineForEmbedding, self).load_weights(mapped())


class ValenMarkerEngine(NativeMarkerEngine):
    def load_weights(self,weights):
        mapped=(('model.'+name.removeprefix('backbone.language_model.'),value)
                for name,value in weights if name.startswith('backbone.language_model.'))
        return super().load_weights(mapped)


def _block_attention_module():
    from torch import nn
    from jevlight.backends.valen_decision15_blocks import block_attention

    class BlockAttention(nn.Module):
        """A full-attention kernel under the trained ``bbox_blocks`` mask.

        A block forward is one complete prefill (the runtime disables chunked
        prefill and prefix caching), so it neither reads nor writes the KV cache.
        """
        def __init__(self, attn, scale):
            super().__init__()
            self.attn, self.scale, self.blocks = attn, scale, None

        def forward(self, query, key, value):
            if self.blocks is None:
                return self.attn(query, key, value)
            attn = self.attn
            q = query.view(-1, attn.num_heads, attn.head_size)
            k = key.view(-1, attn.num_kv_heads, attn.head_size)
            v = value.view(-1, attn.num_kv_heads, attn.head_size)
            output = q.new_zeros(q.shape)
            for start, end, segments in self.blocks:
                output[start:end] = block_attention(q[start:end], k[start:end], v[start:end], segments, self.scale)
            return output.view(-1, attn.num_heads * attn.head_size)
    return BlockAttention


class ValenDecision15MarkerEngine(ValenMarkerEngine):
    """Valen-Decision-1.5 text backbone: block-structured full attention, causal linear attention."""
    def __init__(self, *, vllm_config, prefix='', **kwargs):
        super().__init__(vllm_config=vllm_config, prefix=prefix, **kwargs)
        from pathlib import Path
        from jevlight.backends.valen_decision15_blocks import glue_tokens
        from jevlight.backends.valen_decision15_vllm_runtime import native_tokenizer, published_config
        source = Path(vllm_config.model_config.model)
        published_config(source)
        self.glue = glue_tokens(native_tokenizer(source))
        BlockAttention = _block_attention_module()
        self.block_layers = []
        for layer in self.model.layers:
            if layer.layer_type == 'full_attention':
                attention = layer.self_attn
                attention.attn = BlockAttention(attention.attn, attention.scaling)
                self.block_layers.append(attention.attn)
        self.block_rows = self.causal_rows = 0

    def forward(self, input_ids, positions, intermediate_tensors=None, inputs_embeds=None, **kwargs):
        import torch
        from vllm.forward_context import get_forward_context
        from jevlight.backends.valen_decision15_blocks import prompt_segments
        blocks = None
        metadata = get_forward_context().attn_metadata
        if metadata:
            starts = metadata[self.block_layers[0].attn.layer_name].query_start_loc.tolist()
            ids = input_ids.tolist()
            rows = [(a, b, prompt_segments(ids[a:b], self.glue)) for a, b in zip(starts, starts[1:]) if b > a]
            segmented = sum(segments is not None for _, _, segments in rows)
            if segmented == 0:
                # Startup profiling prompts carry no chat turns and keep the engine kernel.
                self.causal_rows += len(rows)
            elif segmented != len(rows):
                raise ValueError('Every native row must carry its Valen-Decision-1.5 block boundaries')
            else:
                blocks = [(a, b, torch.tensor(segments, device=input_ids.device)) for a, b, segments in rows]
                self.block_rows += len(rows)
        for layer in self.block_layers:
            layer.blocks = blocks
        try:
            return super().forward(input_ids, positions, intermediate_tensors, inputs_embeds, **kwargs)
        finally:
            for layer in self.block_layers:
                layer.blocks = None
