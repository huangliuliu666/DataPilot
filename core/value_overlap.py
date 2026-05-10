import hashlib

import numpy as np
import pandas as pd

from config import VALUE_OVERLAP_CONFIG


class MinHashSignature:

    def __init__(self, num_perm: int = 128, seed: int = 1) -> None:
        self.num_perm = num_perm
        self.seed = seed
        self.mersenne_prime = (1 << 61) - 1
        gen = np.random.RandomState(seed)
        self.a = gen.randint(1, self.mersenne_prime, size=num_perm, dtype=np.uint64)
        self.b = gen.randint(0, self.mersenne_prime, size=num_perm, dtype=np.uint64)

    def generate_signature(self, text_series: pd.Series) -> np.ndarray:
        minhash_values = np.ones(self.num_perm, dtype=np.uint64) * self.mersenne_prime

        for text in text_series.dropna().unique():
            text_str = str(text)
            if text_str.endswith(".0"):
                text_str = text_str[:-2]

            text_bytes = text_str.encode("utf-8")
            raw_hash = int(hashlib.sha1(text_bytes).hexdigest()[:16], 16)
            hashes = (self.a * raw_hash + self.b) % self.mersenne_prime
            minhash_values = np.minimum(minhash_values, hashes)

        return minhash_values

    @staticmethod
    def compute_jaccard(sig_a: np.ndarray, sig_b: np.ndarray) -> float:
        if len(sig_a) != len(sig_b):
            raise ValueError("Signatures must be of same length")
        matching = np.sum(sig_a == sig_b)
        return matching / len(sig_a)


def is_valid_overlap_candidate_column(series: pd.Series, distinct_count: int) -> bool:
    clean_series = series.dropna()
    if len(clean_series) == 0:
        return False

    if pd.api.types.is_bool_dtype(series):
        return False

    is_numeric = False
    numeric_values = None

    if pd.api.types.is_numeric_dtype(series):
        is_numeric = True
        numeric_values = clean_series
    else:
        try:
            numeric_values = pd.to_numeric(clean_series, errors="coerce")
            if numeric_values.notna().mean() > 0.99:
                is_numeric = True
                numeric_values = numeric_values.dropna()
        except Exception:
            pass

    if distinct_count < VALUE_OVERLAP_CONFIG["ENUM_THRESHOLD"]:
        return False

    if is_numeric:
        if distinct_count > 1:
            val_min = numeric_values.min()
            val_max = numeric_values.max()
            sparsity = (val_max - val_min) / distinct_count
            if sparsity < VALUE_OVERLAP_CONFIG["SPARSITY_THRESHOLD"]:
                return False
        else:
            return False

    return True


               
PatentMinHash = MinHashSignature
is_valid_patent_column = is_valid_overlap_candidate_column
