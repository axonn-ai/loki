from typing import Any, Dict, List, Optional, Tuple
from transformers.cache_utils import Cache

import torch

class SparHatCache(Cache):
    """
    Cache based on SparHat mechanism
    """
    def __init__(self, r) -> None:
        self.key_cache: List[torch.Tensor] = [] # Stores the reduced keys for each layer
        self.key_scaling: List[torch.Tensor] = [] # Stores the sum of absolute values of the full keys
        self.value_cache: List[torch.Tensor] = []
        self.top_r = r 
        print (f"Cache initialized with top_r = {r}")

    def __get_top_r(self, t, dim = -1):
        # Get the top-r absolute values of the keys along the dh dimension
        i1 = torch.topk(torch.abs(t), self.top_r, dim).indices

        # Zero out all indices other than the top-r 
        # TODO: Make this an actual sparse matrix
        t_sparse = torch.full_like(t, fill_value=0)
        t_sparse.scatter_(dim, i1, t.gather(dim, i1))

        return t_sparse

    def __get_top_r_l1(self, t, dim = -1):
        # Get the first 512 rows
        t_initial = t[:,:,:2048,:]
        l1_norms = torch.abs(t_initial).sum(dim=-2, keepdim=True)

        imp_cols = torch.topk(l1_norms, self.top_r, -1, sorted=True).indices
        torch.set_printoptions(threshold=float('inf'))
        print (imp_cols)
        imp_cols = imp_cols.expand(*t.shape[:-1], self.top_r)

        # TODO: Make this an actual sparse matrix
        t_sparse = torch.full_like(t, fill_value=0)
        t_sparse.scatter_(dim, imp_cols, t.gather(dim, imp_cols))
        
        return t_sparse

    def __get_top_r_ss(self, t, dim = -1):
        # Reshape the tensor to have blocks of 4 in the last dimension
        top_r_sparse_t = self.__get_top_r(t)

        reshaped_t = t.view(*t.shape[:-1], dim, 4)

        # Get the top 2 values for every block of 4 values (4:2 sparsity)
        i1 = torch.topk(torch.abs(reshaped_t), 2, -1).indices

        # Zero out all indices expect the top ones 
        t_sparse = torch.full_like(reshaped_t, fill_value=0)
        t_sparse.scatter_(dim, i1, reshaped_t.gather(dim, i1))
        
        # Reshape the tensor back to the original shape
        t_sparse = t_sparse.view(t.shape)

        # Caclulate scaling - does not work
        t_scaling = torch.where((t_sparse!= 0) & (top_r_sparse_t!= 0), t_sparse, torch.tensor(0))
        t_scaling = torch.abs(t_scaling).sum(-1, keepdim=True)

        # Recency factor
        #select_t_sparse = t_sparse[:,:,2048:,:]
        #select_topr_t_sparse = top_r_sparse_t[:,:,:1024,:]
        #select_topr_t_sparse = t[:,:,:2048,:]
        #t_sparse = torch.cat([select_t_sparse, select_topr_t_sparse], dim=2)
        #t_sparse = torch.cat([select_topr_t_sparse, select_t_sparse], dim=2)

        torch.set_printoptions(threshold=float('inf'))

        t_switches = torch.where((t_sparse!= 0) & (top_r_sparse_t!= 0), torch.tensor(1), torch.tensor(0))

        
        _,mins = t_switches.sum(dim=-1).min(dim=-1)
        _,maxs = t_switches.sum(dim=-1).max(dim=-1)

        print (f"{mins}, {maxs}")

        return t_sparse

    def update(
        self,
        key_states: torch.Tensor,
        value_states: torch.Tensor,
        layer_idx: int,
        cache_kwargs: Optional[Dict[str, Any]] = None,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Updates the cache with the new `key_states` and `value_states` for the layer `layer_idx`.

        Parameters:
            key_states (`torch.Tensor`):
                The new key states to cache.
            value_states (`torch.Tensor`):
                The new value states to cache.
            layer_idx (`int`):
                The index of the layer to cache the states for.
            cache_kwargs (`Dict[str, Any]`, `optional`):
                Additional arguments for the cache subclass. These are specific to each subclass and allow new types of
                cache to be created.

        Return:
            A tuple containing the updated key and value states.
        """
        if len(self.key_cache) <= layer_idx:
            # Empty cache
            key_sparse = self.__get_top_r(key_states)
            self.key_cache.append(key_sparse)
            self.key_scaling.append(torch.abs(key_states).sum(-1, keepdim=True))
            self.value_cache.append(value_states)
        else:
            # Growing cache
            key_sparse, key_scale = self.__get_top_r(key_states)
            self.key_cache[layer_idx] = torch.cat([self.key_cache[layer_idx], key_sparse], dim=-2)
            self.key_scaling[layer_idx] = torch.cat([self.key_scaling[layer_idx], (torch.abs(key_states).sum(-1, keepdim=True))], dim=-2)
            self.value_cache[layer_idx] = torch.cat([self.value_cache[layer_idx], value_states], dim=-2)          
        
        return self.key_cache[layer_idx], self.key_scaling[layer_idx], self.value_cache[layer_idx]

    def get_seq_length(self, layer_idx: Optional[int] = 0) -> int:
        """Returns the sequence length of the cached states. A layer index can be optionally passed."""
        if len(self.key_cache) <= layer_idx:
            return 0
        return self.key_cache[layer_idx].shape[-2]

    def get_max_length(self) -> Optional[int]:
        """Returns the maximum sequence length of the cached states, if there is any."""
        return None

    def get_usable_length(self, new_seq_length: int, layer_idx: Optional[int] = 0) -> int:
        """Given the sequence length of the new inputs, returns the usable length of the cache."""
        # Cache without size limit -> all cache is usable
        # Cache with size limit -> if the length cache plus the length of the new inputs is larger the maximum cache
        #   length, we will need to evict part of the cache (and thus not all cache is usable)
        max_length = self.get_max_length()
        previous_seq_length = self.get_seq_length(layer_idx)
        if max_length is not None and previous_seq_length + new_seq_length > max_length:
            return max_length - new_seq_length
        return previous_seq_length

def test_spar_hat():
    cache = SparHatCache(64)

    torch.set_printoptions(threshold=float('inf'))
    test_tensor = torch.rand(1, 4, 8, 16)
    print (test_tensor)

    sparse_test_tensor = (cache.get_top_r_l1(test_tensor))

    print (sparse_test_tensor)


if __name__ == "__main__":
    test_spar_hat()
