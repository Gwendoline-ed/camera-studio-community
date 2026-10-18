import base64
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from tiny2.gwen import GwenClient, local_profile, make_request, parse_reply, DEFAULT_MODEL, MAX_IMAGE
from tiny2.manual_drag import ManualDrag
from tiny2.app import Studio
from types import SimpleNamespace

PNG = b'\x89PNG\r\n\x1a\nsynthetic-payload'


def response(**changes):
    data = dict(frame_id='frame-1', answer='Hier liegen die gesuchten Stellen.', uncertain=False,
                markers=[dict(label='Pin 1', x=250, y=600), dict(label='Pin 30', x=750, y=400)])
    data.update(changes)
    return json.dumps(data)


class GwenProtocolTests(unittest.TestCase):
    def test_only_current_image_and_bounded_text_history_sent(self):
        history = [{'role': 'user', 'content': f'Frage {n}', 'images': ['old-photo']} for n in range(20)]
        request = make_request('local-model', 'Markiere Pin 1', PNG, 'frame-1', history)
        self.assertEqual(len(request['messages']), 10)
        self.assertFalse(any('images' in m for m in request['messages'][:-1]))
        self.assertEqual(base64.b64decode(request['messages'][-1]['images'][0]), PNG)
        self.assertIn('frame-1', request['messages'][-1]['content'])
        self.assertNotIn('tools', request)

    def test_invalid_or_oversized_input_rejected(self):
        for prompt, data in [('', PNG), ('x' * 4001, PNG), ('test', b'bad'),
                             ('test', PNG + bytes(MAX_IMAGE))]:
            with self.assertRaises(ValueError): make_request('model', prompt, data, 'id')

    def test_valid_markers_keep_original_normalized_coordinates(self):
        result = parse_reply(response(), 'frame-1')
        self.assertEqual(result['markers'][0], dict(label='Pin 1', x=250, y=600))
        self.assertEqual(len(result['markers']), 2)

    def test_uncertain_or_wrong_image_never_draws_pins(self):
        for raw in (response(uncertain=True), response(uncertain='false'), response(frame_id='old-photo')):
            self.assertEqual(parse_reply(raw, 'frame-1')['markers'], [])

    def test_invalid_coordinates_discard_all_markers(self):
        for value in (-1, 1001, float('nan'), True, '500'):
            result = parse_reply(response(markers=[dict(label='Pin 1', x=200, y=200),
                                                  dict(label='Pin 30', x=value, y=500)]), 'frame-1')
            self.assertEqual(result['markers'], [])

    def test_plain_reply_retains_text_without_fake_annotations(self):
        result = parse_reply('Bitte nenne den IC-Aufdruck.', 'frame-1')
        self.assertIn('IC-Aufdruck', result['answer']); self.assertEqual(result['markers'], [])
        self.assertEqual(len(parse_reply('```json\n' + response() + '\n```', 'frame-1')['markers']), 2)

    def test_model_is_explicit_and_private_webui_is_not_inspected(self):
        with patch('tiny2.gwen.integrations.load',return_value={'model':'chosen-vision'}):
            self.assertEqual(local_profile('/unused/private/folder'),'chosen-vision')
        with patch('tiny2.gwen.integrations.load',return_value={'model':''}):
            self.assertEqual(local_profile(),DEFAULT_MODEL)

    def test_vision_checked_before_any_image_request(self):
        client = GwenClient()
        with patch.object(client, 'request', return_value={'capabilities': ['completion']}) as request:
            with self.assertRaisesRegex(RuntimeError, 'keine Kamerabilder'): client.chat('test', PNG, 'frame-1')
            self.assertEqual(request.call_count, 1)
            self.assertEqual(request.call_args.args[0], '/api/show')

    def test_complete_response_roundtrip_and_truncated_response_rejected(self):
        client = GwenClient()
        for done_reason, good in [('stop', True), ('length', False)]:
            replies = [{'capabilities': ['vision']}, {'done': True, 'done_reason': done_reason,
                        'message': {'content': response()}}]
            with patch.object(client, 'request', side_effect=replies):
                if good: self.assertEqual(len(client.chat('test', PNG, 'frame-1')['markers']), 2)
                else:
                    with self.assertRaises(ValueError): client.chat('test', PNG, 'frame-1')

    def test_cancelled_request_cannot_send_later(self):
        client = GwenClient(); client.cancel()
        with patch('tiny2.gwen.http.client.HTTPConnection') as connection:
            with self.assertRaises(InterruptedError): client.chat('test', PNG, 'frame-1')
            connection.return_value.request.assert_not_called()

    def test_stale_camera_frame_is_not_reused_after_restart_or_pause(self):
        app = SimpleNamespace(preview=SimpleNamespace(pipeline=object(), generation=3),
                              last_frame=('texture', 3, 10), end_manual_drag=lambda: None)
        with patch('tiny2.app.time.monotonic', return_value=11):
            self.assertEqual(Studio.camera_snapshot(app), 'texture')
            app.preview.generation = 4
            with self.assertRaises(ValueError): Studio.camera_snapshot(app)
            app.preview.generation = 3; app.preview.pipeline = None
            with self.assertRaises(ValueError): Studio.camera_snapshot(app)
        app.preview.pipeline = object()
        with patch('tiny2.app.time.monotonic', return_value=15):
            with self.assertRaises(ValueError): Studio.camera_snapshot(app)


if __name__ == '__main__': unittest.main()
