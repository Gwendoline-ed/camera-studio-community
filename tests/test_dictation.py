import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock
from tiny2.dictation import Recorder, Transcriber, MAX_PCM, whisper_paths
from tiny2.gwen_window import GwenWindow


class DictationTests(unittest.TestCase):
    def test_runtime_uses_explicit_local_model_without_download(self):
        from tiny2 import integrations
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory);model=home/'model';model.mkdir()
            (model/'model.bin').write_bytes(b'model');(model/'config.json').write_text('{}')
            python=home/'python';python.write_text('');python.chmod(0o700)
            with patch('tiny2.dictation.integrations.load',return_value=dict(integrations.DEFAULTS)):
                with self.assertRaises(RuntimeError):whisper_paths()
            settings=dict(integrations.DEFAULTS,whisper_python=str(python),whisper_model=str(model))
            with patch('tiny2.dictation.integrations.load',return_value=settings):
                self.assertEqual(whisper_paths(),(python,model))

    def test_empty_oversized_and_cancelled_recordings_never_spawn_worker(self):
        transcriber = Transcriber()
        with patch('tiny2.dictation.subprocess.Popen') as spawn:
            for data in (b'', b'x', bytes(MAX_PCM + 2)):
                with self.assertRaises(ValueError): transcriber.transcribe(data)
            transcriber.cancel()
            with self.assertRaises(InterruptedError): transcriber.transcribe(bytes(32000))
            spawn.assert_not_called()

    def test_recorder_caps_ram_and_finishes_once(self):
        recorder = Recorder(lambda _: None, lambda _: None)
        data = bytes(500000)
        buffer = SimpleNamespace(map=lambda _: (True, SimpleNamespace(data=data)), unmap=lambda _: None)
        sink = SimpleNamespace(emit=lambda _: SimpleNamespace(get_buffer=lambda: buffer))
        with patch('tiny2.dictation.GLib.idle_add') as idle:
            for _ in range(8): recorder.sample(sink, recorder.generation)
            self.assertEqual(len(recorder.data), MAX_PCM)
            self.assertEqual(idle.call_count, 1)
        old_generation = recorder.generation
        self.assertEqual(len(recorder.stop()), MAX_PCM)
        recorder.sample(sink, old_generation)
        self.assertEqual(recorder.data, b'')

    def test_recorded_text_is_added_to_composer_and_not_sent(self):
        entry = Mock(); entry.get_text.return_value = 'Bitte'
        window = SimpleNamespace(closed=False, entry=entry, status=Mock(), work=lambda fn, done: done(fn()))
        with patch('tiny2.gwen_window.Transcriber') as transcriber:
            transcriber.return_value.transcribe.return_value = 'markiere Pin eins.'
            GwenWindow.recorded(window, bytes(32000))
        entry.set_text.assert_called_once_with('Bitte markiere Pin eins.')
        self.assertIn('prüfen', window.status.set_text.call_args.args[0])
        self.assertFalse(hasattr(window, 'client'))

    def test_cancel_kills_only_the_active_transcription_process(self):
        transcriber = Transcriber(); process = Mock(); process.poll.return_value = None
        transcriber.process = process; transcriber.cancel()
        process.kill.assert_called_once()
        self.assertTrue(transcriber.cancelled.is_set())


if __name__ == '__main__': unittest.main()
