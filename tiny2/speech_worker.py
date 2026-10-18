"""Offline Whisper worker. Raw 16 kHz mono signed PCM arrives on stdin."""
from .i18n import tr as _t
import json
import os
from pathlib import Path
import sys
import time


def main():
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['OMP_NUM_THREADS'] = '2'
    model_path=Path(sys.argv[1]);guard_path=sys.argv[2]
    pcm = sys.stdin.buffer.read(60 * 16000 * 2 + 1)
    if not pcm or len(pcm) > 60 * 16000 * 2 or len(pcm) % 2:
        raise ValueError(_t('Ungültige oder zu lange Tonaufnahme.'))
    lease=None
    if guard_path:
        sys.path.insert(0, guard_path)
        from guard_common import Lease, check_memory
        lease = Lease(); deadline = time.monotonic() + 20
        while not lease.try_acquire():
            if time.monotonic() >= deadline:
                raise RuntimeError(_t('Der lokale KI-Dienst rechnet gerade. Bitte später diktieren.'))
            time.sleep(.2)
    try:
        if guard_path:check_memory()
        import numpy as np
        samples = np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768
        if np.max(np.abs(samples)) < .003:
            print(json.dumps({'text': ''})); return
        from faster_whisper import WhisperModel
        model = WhisperModel(str(model_path), device='cpu', compute_type='int8',
                             cpu_threads=2, num_workers=1, local_files_only=True)
        segments, _ = model.transcribe(samples, language='de', beam_size=3, vad_filter=True,
                                       condition_on_previous_text=False)
        print(json.dumps({'text': ' '.join(s.text.strip() for s in segments)}, ensure_ascii=False))
    finally:
        if lease:lease.release()


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print(json.dumps({'error': str(error)})); sys.exit(1)
