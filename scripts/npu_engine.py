"""
npu_engine.py - NPU加速引擎(TF-IDF语义搜索+ONNX DirectML+批量质量分类)
路径：scripts/npu_engine.py
版本：v2.3.7

三路径: sklearn TfidfVectorizer(主) / 纯numpy TF-IDF(备选) / ONNX DirectML(可选加速)
"""
import os
import re
import time
from collections import Counter
import numpy as np

# --- Optional dependencies (engine degrades gracefully) ---
try:
    import onnxruntime as ort; HAS_ONNX = True
except ImportError:
    ort = None; HAS_ONNX = False

try:
    from sklearn.feature_extraction.text import TfidfVectorizer; HAS_SKLEARN = True
except ImportError:
    TfidfVectorizer = None; HAS_SKLEARN = False

try:
    import numba  # noqa: F401
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False


# =====================================================================
# Pure-numpy TF-IDF (Chinese bigram tokenization, zero external deps)
# =====================================================================

def _tokenize_cn(text):
    """Whitespace tokens + overlapping bigrams on Chinese character runs."""
    tokens = []
    for part in str(text).split():
        cn = re.findall(r'[一-鿿]+', part)
        for seg in cn:
            tokens.append(seg) if len(seg) == 1 else [
                tokens.append(seg[i:i + 2]) for i in range(len(seg) - 1)]
        tokens.extend(re.sub(r'[一-鿿]+', ' ', part).split())
    return tokens


class _NumpyTfidf(object):
    """Self-contained TF-IDF vectorizer. Only numpy required."""

    def __init__(self, max_features=5000):
        self.max_features = max_features
        self.vocabulary_ = {}
        self.idf_ = None

    def _build_tf(self, texts):
        tokenized = [_tokenize_cn(t) for t in texts]
        counter = Counter()
        for tk in tokenized:
            counter.update(tk)
        top = [t for t, _ in counter.most_common(self.max_features)]
        self.vocabulary_ = {t: i for i, t in enumerate(top)}
        V = len(self.vocabulary_)
        if V == 0:
            return np.zeros((len(texts), 0), dtype=np.float32)
        tf = np.zeros((len(texts), V), dtype=np.float32)
        for i, tk in enumerate(tokenized):
            for t in tk:
                idx = self.vocabulary_.get(t)
                if idx is not None:
                    tf[i, idx] += 1.0
        return tf

    def fit_transform(self, texts):
        tf = self._build_tf(texts)
        if tf.shape[1] == 0:
            self.idf_ = np.array([], dtype=np.float32)
            return tf
        tf /= np.maximum(tf.sum(axis=1, keepdims=True), 1.0)
        df = (tf > 0).sum(axis=0).astype(np.float32)
        self.idf_ = np.log((len(texts) + 1.0) / (df + 1.0)) + 1.0
        return tf * self.idf_[np.newaxis, :]

    def transform(self, texts):
        tf = self._build_tf(texts)
        if tf.shape[1] == 0:
            return tf
        tf /= np.maximum(tf.sum(axis=1, keepdims=True), 1.0)
        return tf * self.idf_[np.newaxis, :]


# =====================================================================
# ONNX DirectML helpers
# =====================================================================

def _detect_dml():
    if not HAS_ONNX:
        return False
    try:
        return 'DmlExecutionProvider' in ort.get_available_providers()
    except Exception:
        return False


def _load_onnx_session(model_path):
    for provs in (['DmlExecutionProvider', 'CPUExecutionProvider'],
                   ['CPUExecutionProvider']):
        try:
            return ort.InferenceSession(model_path, providers=provs)
        except Exception:
            continue
    return None


def _cosine_batch(query_vec, doc_matrix):
    """query_vec (D,), doc_matrix (N,D) -> (N,) cosine scores via matmul."""
    q = query_vec.ravel().astype(np.float32)
    qn = float(np.linalg.norm(q))
    if qn < 1e-10:
        return np.zeros(doc_matrix.shape[0], dtype=np.float32)
    dn = np.maximum(np.linalg.norm(doc_matrix, axis=1), 1e-10)
    return (np.dot(doc_matrix, q) / (qn * dn)).astype(np.float32)


# =====================================================================
# Pre-compiled regexes (module level, compiled once)
# =====================================================================

_KW_RE = re.compile('|'.join([
    '政策', '耕地', '指标', '补偿', '项目', '规划', '资金',
    '土地', '农村', '农业', '农民', '乡村', '建设', '管理',
    '标准', '方案', '意见', '措施', '保护', '开发', '整治']))

_NUM_RE = re.compile(r'\d+')

_STRUCT_RE = re.compile(
    r'[一二三四五六七八九十]+[、．.]|'
    r'（[一二三四五六七八九十]+）|'
    r'\d+[\.\、]|'
    r'第[一二三四五六七八九十\d]+[章节条]|'
    r'[：:。；;]')


# =====================================================================
# NPUEngine
# =====================================================================

class NPUEngine(object):
    """NPU加速引擎。零API成本/零网络依赖/零模型下载。

    主路径(sklearn/numpy-TFIDF)永远可用,ONNX模型仅作可选加速。
    """

    _MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                              'data', 'models')

    def __init__(self):
        self._dml_available = _detect_dml()
        self._providers = ort.get_available_providers() if HAS_ONNX else []

        self._onnx_session = None
        onnx_path = os.path.join(self._MODEL_DIR, 'embedding_model.onnx')
        if self._dml_available and os.path.isfile(onnx_path):
            self._onnx_session = _load_onnx_session(onnx_path)

        self._vectorizer = None     # sklearn TfidfVectorizer
        self._numpy_tfidf = None    # _NumpyTfidf fallback
        self._corpus_texts = None
        self._corpus_matrix = None  # (N, D) float32

    # -- Public API ----------------------------------------------------------

    def build_index(self, texts):
        """Build/replace search index from a text corpus."""
        if not texts:
            return False
        self._corpus_texts = list(texts)
        if HAS_SKLEARN:
            self._vectorizer = TfidfVectorizer(
                max_features=5000, analyzer='char_wb', ngram_range=(2,4),
                dtype=np.float32)
            self._corpus_matrix = self._vectorizer.fit_transform(
                self._corpus_texts).toarray()
        else:
            self._numpy_tfidf = _NumpyTfidf(max_features=5000)
            self._corpus_matrix = self._numpy_tfidf.fit_transform(
                self._corpus_texts)
        return True

    def semantic_search(self, query, texts=None, top_k=5):
        """TF-IDF vectorize query -> cosine similarity -> top-k results.

        Returns [[index, score], ...] sorted by descending score.
        """
        if texts is not None:
            self.build_index(texts)
        if self._corpus_matrix is None or self._corpus_matrix.shape[0] == 0:
            return []

        try:
            if self._vectorizer is not None:
                query_vec = self._vectorizer.transform([query]).toarray()
            elif self._numpy_tfidf is not None:
                query_vec = self._numpy_tfidf.transform([query])
            else:
                return []
        except (ValueError, AttributeError):
            return []

        scores = _cosine_batch(query_vec, self._corpus_matrix)
        k = min(top_k, len(scores))
        if k == 0:
            return []
        top_idx = np.argpartition(-scores, k)[:k] if k < len(scores) else np.arange(len(scores))
        top_scores = scores[top_idx]
        order = np.argsort(-top_scores)
        return [[int(top_idx[o]), float(top_scores[o])] for o in order]

    def hybrid_search(self, query, texts=None, top_k=5):
        """Hybrid search: TF-IDF dense retrieval + BM25 re-ranking.

        Steps:
          1. char_wb TF-IDF -> cosine similarity -> top-50 candidates
          2. BM25 re-rank within top-50 (IDF-weighted keyword overlap)
          3. Merge scores (0.4 dense + 0.6 BM25) -> return top-k

        Returns [[index, score], ...] sorted by descending merged score.
        """
        if texts is not None:
            self.build_index(texts)
        if self._corpus_matrix is None or self._corpus_matrix.shape[0] == 0:
            return []

        # Step 1: Dense TF-IDF retrieval -> top-50
        try:
            if self._vectorizer is not None:
                query_vec = self._vectorizer.transform([query]).toarray()
            elif self._numpy_tfidf is not None:
                query_vec = self._numpy_tfidf.transform([query])
            else:
                return []
        except (ValueError, AttributeError):
            return []

        dense_scores = _cosine_batch(query_vec, self._corpus_matrix)
        n_docs = len(dense_scores)
        if n_docs == 0:
            return []

        k_dense = min(50, n_docs)
        if k_dense < n_docs:
            top_idx = np.argpartition(-dense_scores, k_dense)[:k_dense]
        else:
            top_idx = np.arange(n_docs)

        # Step 2: BM25 re-ranking on top-50 candidates
        top_texts = [str(self._corpus_texts[i]) for i in top_idx]
        query_tokens = _tokenize_cn(query)
        if not query_tokens:
            # Fallback: dense scores only
            final_idx = top_idx
            final_scores = dense_scores[top_idx]
        else:
            doc_tokens = [_tokenize_cn(t) for t in top_texts]
            # IDF on top-50 subset
            N = len(doc_tokens)
            df = {}
            for tokens in doc_tokens:
                for t in set(tokens):
                    df[t] = df.get(t, 0) + 1

            k1, b_param = 1.5, 0.75
            doc_lens = np.array([len(tk) for tk in doc_tokens], dtype=np.float32)
            avgdl = max(float(doc_lens.mean()), 1.0)

            bm25_scores = np.zeros(N, dtype=np.float32)
            for i, tokens in enumerate(doc_tokens):
                tf_dict = {}
                for t in tokens:
                    tf_dict[t] = tf_dict.get(t, 0) + 1
                score = 0.0
                for qt in query_tokens:
                    df_t = df.get(qt, 0)
                    if df_t == 0:
                        continue
                    idf = float(np.log((N - df_t + 0.5) / (df_t + 0.5) + 1.0))
                    tf = tf_dict.get(qt, 0)
                    if tf == 0:
                        continue
                    score += idf * (tf * (k1 + 1)) / (
                        tf + k1 * (1 - b_param + b_param * doc_lens[i] / avgdl))
                bm25_scores[i] = score

            # Normalize to [0,1] for merging
            bm25_max = float(bm25_scores.max())
            bm25_norm = bm25_scores / bm25_max if bm25_max > 0 else bm25_scores

            dense_subset = dense_scores[top_idx]
            dense_max = float(dense_subset.max())
            dense_norm = dense_subset / dense_max if dense_max > 0 else dense_subset

            # Merge: 0.4 dense + 0.6 BM25
            merged = 0.4 * dense_norm + 0.6 * bm25_norm
            final_order = np.argsort(-merged)
            final_idx = top_idx[final_order]
            final_scores = merged[final_order]

        k = min(top_k, len(final_idx))
        return [[int(final_idx[i]), float(final_scores[i])] for i in range(k)]

    def get_embedding_dim(self):
        """Return the embedding dimension of the current index."""
        if self._corpus_matrix is not None:
            return int(self._corpus_matrix.shape[1])
        return 0

    def is_hybrid_ready(self):
        """Check if hybrid search is available (requires built index)."""
        return (self._corpus_matrix is not None
                and len(self._corpus_texts or []) > 0)

    def quality_classify(self, title, excerpt):
        """Score a single item (1-5). Convenience wrapper."""
        scores = self.quality_classify_batch([title], [excerpt])
        return scores[0] if scores else 3

    def quality_classify_batch(self, titles, excerpts):
        """Batch quality scoring: 5 numpy-vectorized features -> 1-5 integer.

        Features: excerpt length, title informativeness, domain keyword density,
                  numeric-data density, structure completeness.
        """
        n = len(titles)
        if n == 0:
            return []

        ex_lens = np.array([len(str(e)) for e in excerpts], dtype=np.float32)
        tl_lens = np.array([len(str(t)) for t in titles], dtype=np.float32)

        len_score = np.clip(ex_lens / 300.0, 0.0, 1.5)
        title_score = np.clip(tl_lens / 20.0, 0.0, 1.0)

        kw_counts = np.array([float(len(_KW_RE.findall(str(e))))
                              for e in excerpts], dtype=np.float32)
        kw_density = np.where(ex_lens > 0,
                              kw_counts / np.maximum(ex_lens, 1.0) * 100.0, 0.0)
        kw_score = np.clip(kw_density / 5.0, 0.0, 1.5)

        num_counts = np.array([float(len(_NUM_RE.findall(str(e))))
                               for e in excerpts], dtype=np.float32)
        num_density = np.where(ex_lens > 0,
                               num_counts / np.maximum(ex_lens, 1.0) * 100.0, 0.0)
        data_score = np.clip(num_density / 3.0, 0.0, 1.0)

        struct_counts = np.array([float(len(_STRUCT_RE.findall(str(e))))
                                  for e in excerpts], dtype=np.float32)
        struct_score = np.clip(struct_counts / 5.0, 0.0, 1.0)

        raw = (len_score * 0.25 + title_score * 0.15 +
               kw_score * 0.25 + data_score * 0.15 + struct_score * 0.20)
        return np.clip(np.rint(raw * 5.0), 1.0, 5.0).astype(int).tolist()

    def get_status(self):
        """Hardware capabilities and engine state."""
        return {
            "dml_available": self._dml_available,
            "providers": self._providers,
            "onnx_model_loaded": self._onnx_session is not None,
            "sklearn_available": HAS_SKLEARN,
            "numba_available": HAS_NUMBA,
            "numpy_version": np.__version__,
            "index_built": self._corpus_matrix is not None,
            "corpus_size": len(self._corpus_texts) if self._corpus_texts else 0,
            "vector_dim": int(self._corpus_matrix.shape[1])
                          if self._corpus_matrix is not None else 0,
            "engine_mode": self._engine_mode(),
            "capabilities": ["semantic_search", "quality_classify_batch",
                             "build_index", "benchmark"],
        }

    def benchmark(self, n_items=1000, n_queries=10):
        """Speed test with synthetic data. Returns throughput metrics."""
        rng = np.random.RandomState(42)
        _P = ["乡村振兴", "耕地保护", "项目规划", "资金管理", "土地整治",
              "农村建设", "农业现代化", "政策扶持", "生态保护", "产业融合"]

        syn_corpus = ["政策文档%d %s %s %s" % (
            i, _P[rng.randint(0, 10)], _P[rng.randint(0, 10)],
            _P[rng.randint(0, 10)]) for i in range(n_items)]

        t0 = time.perf_counter()
        self.build_index(syn_corpus)
        t_idx = time.perf_counter() - t0

        queries = ["查询 %s %s" % (_P[rng.randint(0, 10)],
                                   _P[rng.randint(0, 10)])
                   for _ in range(n_queries)]
        t0 = time.perf_counter()
        for q in queries:
            self.semantic_search(q, top_k=10)
        t_search = time.perf_counter() - t0

        _tpl = "第%d号%s实施方案 涵盖%s指标 %s规范 %s标准"
        syn_titles = [_tpl % (i, _P[rng.randint(0, 10)], _P[rng.randint(0, 10)],
                              _P[rng.randint(0, 10)], _P[rng.randint(0, 10)])
                      for i in range(n_items)]
        syn_excerpts = [
            "本文档详细说明了第%d项政策的实施方案，包含耕地保护指标、"
            "项目资金管理规范、补偿标准等关键内容。" % i
            for i in range(n_items)]

        t0 = time.perf_counter()
        self.quality_classify_batch(syn_titles, syn_excerpts)
        t_cls = time.perf_counter() - t0

        return {
            "corpus_size": n_items,
            "engine_mode": self._engine_mode(),
            "index_time_s": round(t_idx, 3),
            "index_items_per_sec": round(n_items / max(t_idx, 0.001)),
            "search_queries": n_queries,
            "search_total_s": round(t_search, 3),
            "search_ms_per_query": round(t_search / n_queries * 1000, 1),
            "classify_total_s": round(t_cls, 3),
            "classify_items_per_sec": round(n_items / max(t_cls, 0.001)),
        }

    # -- Internal -------------------------------------------------------------

    def _engine_mode(self):
        if self._onnx_session is not None:
            return "ONNX_DirectML"
        return "sklearn_TFIDF" if HAS_SKLEARN else "numpy_TFIDF"
