"""
hardware_saturate.py - 硬件满载引擎(GPU持续推理+CPU多核计算)
路径：scripts/hardware_saturate.py
版本：v2.3.7-part7
"""
import onnxruntime as ort, numpy as np, json, re, sqlite3, time, gc, psutil, os, sys


def tokenize(text, vocab):
    cn = re.findall(r'[一-鿿]+', text)
    return [vocab.get(seg[i:i+2], 0) for seg in cn for i in range(len(seg)-1)][:256] or [0]


def gpu_saturate(seconds=120):
    """GPU持续满载: 大batch ONNX推理+矩阵乘法,持续N秒"""
    print(f'[GPU] Loading ONNX model...')
    session = ort.InferenceSession('data/models/embedding_model.onnx',
                                   providers=['DmlExecutionProvider', 'CPUExecutionProvider'])
    print(f'[GPU] Provider: {session.get_providers()[0]}')

    with open('data/models/domain_vocab.json', 'r', encoding='utf-8') as f:
        vocab = json.load(f)

    db = sqlite3.connect('data/database/knowledge_base.db')
    c = db.cursor()
    c.execute("SELECT title,original_excerpt FROM knowledge_points WHERE review_status='confirmed' LIMIT 2000")
    rows = c.fetchall()
    db.close()
    texts = [(r[0] or '') + ' ' + (r[1] or '')[:500] for r in rows]
    print(f'[GPU] {len(texts)} documents, {seconds}s target')

    max_len = min(256, max(len(tokenize(t, vocab)) for t in texts))
    inp = np.zeros((len(texts), max_len), dtype=np.int64)
    for i, t in enumerate(texts):
        ids = tokenize(t, vocab)[:max_len]
        inp[i, :len(ids)] = ids

    print(f'[GPU] Batch: {inp.shape}, starting sustained load...')
    t0 = time.time()
    rounds = 0
    while time.time() - t0 < seconds:
        out = session.run(None, {'input_ids': inp})[0]
        vecs = out.mean(axis=1).astype(np.float32)
        vecs = vecs / (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-10)
        sim = np.dot(vecs, vecs.T)
        rounds += 1
        if rounds % 50 == 0:
            print(f'[GPU] {time.time()-t0:.0f}s: {rounds} rounds, GPU active')

    t1 = time.time()
    print(f'[GPU] DONE: {rounds} rounds in {t1-t0:.1f}s ({rounds/(t1-t0):.0f} rounds/s)')


def cpu_saturate(seconds=120, workers=None):
    """CPU持续满载: 多进程文本处理+Numpy矩阵运算"""
    import multiprocessing as mp
    workers = workers or mp.cpu_count()
    print(f'[CPU] Starting {workers} workers for {seconds}s...')

    def worker(duration):
        t0 = time.time()
        ops = 0
        while time.time() - t0 < duration:
            mat = np.random.randn(200, 200).astype(np.float32)
            for _ in range(20):
                mat = np.dot(mat, mat.T)
            ops += 1
        return ops

    with mp.Pool(workers) as pool:
        results = pool.map(worker, [seconds] * workers)

    print(f'[CPU] DONE: {workers} workers, {sum(results)} total ops')


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--mode', default='both', choices=['gpu', 'cpu', 'both'])
    p.add_argument('--seconds', type=int, default=120)
    p.add_argument('--workers', type=int, default=None)
    args = p.parse_args()

    print(f'=== Hardware Saturate: {args.mode}, {args.seconds}s ===')
    print(f'CPU cores: {os.cpu_count()}, RAM: {psutil.virtual_memory().total/1024**3:.0f}GB')

    if args.mode in ('gpu', 'both'):
        gpu_saturate(args.seconds)
    if args.mode in ('cpu', 'both'):
        cpu_saturate(args.seconds, args.workers)

    gc.collect()
    print(f'Final RAM: {psutil.virtual_memory().percent}%')
