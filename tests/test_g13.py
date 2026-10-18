import json
from pathlib import Path
import socket
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tiny2.g13_input import Input, State, Subscription, verify_profile, PROFILE_ID, PROFILE_NAME
from test_wheel_zoom import StudioFlowCase
from test_manual_drag import MotionCamera, MouseGesture, Toggle
from gui_integration import pump


def state(stick=(147, 127), keys=(), **values):
    return State.parse(dict(kind='state', profile_id=PROFILE_ID, profile=PROFILE_NAME,
                            stick=list(stick), keys=list(keys), mr_state='idle', **values))


PROFILE = dict(id=PROFILE_ID, name=PROFILE_NAME, slot=2, bindings={}, macros={}, stick_mode='keys')


class G13InputTests(unittest.TestCase):
    def test_offcenter_rest_is_neutral_then_axes_are_scaled_and_bounded(self):
        controller = Input()
        self.assertIsNone(controller.evaluate(state(), True)['motion'])
        self.assertEqual(controller.center, (147, 127))
        controller.speed = 25
        pan, tilt, release = controller.evaluate(state((255, 0)), True)['motion']
        self.assertLess(pan, 0); self.assertGreater(tilt, 0)
        self.assertLessEqual((pan * pan + tilt * tilt) ** .5, 25.00001)
        controller.evaluate(state(), True); self.assertTrue(release.is_set())

    def test_stick_held_at_activation_cannot_move_until_returned_to_center(self):
        controller = Input()
        for _ in range(3): self.assertIsNone(controller.evaluate(state((255, 127)), True)['motion'])
        controller.evaluate(state(), True)
        self.assertIsNotNone(controller.evaluate(state((255, 127)), True)['motion'])

    def test_focus_loss_profile_change_recording_and_stale_data_stop_motion(self):
        from dataclasses import replace
        for bad, focused in [(None, True), (state(), False),
                (replace(state(), profile_id='profile-1'), True),
                (replace(state(), mr_state='recording'), True),
                (replace(state(), received=time.monotonic()-1), True)]:
            controller = Input(); controller.evaluate(state(), True)
            release = controller.evaluate(state((255, 127)), True)['motion'][2]
            result = controller.evaluate(bad, focused)
            self.assertTrue(release.is_set()); self.assertFalse(controller.armed)
            self.assertIsNone(result['motion']); self.assertFalse(result['actions'])
            self.assertIsNone(controller.evaluate(state((255, 127)), True)['motion'])

    def test_buttons_are_edges_and_fine_mode_reduces_speed(self):
        controller = Input(); controller.evaluate(state(), True)
        self.assertEqual(controller.evaluate(state(keys=['G12']), True)['actions'], ['gwen'])
        self.assertEqual(controller.evaluate(state(keys=['G12']), True)['actions'], [])
        normal = controller.evaluate(state((255,127)), True)['motion'][0]
        fine = controller.evaluate(state((255,127), ['G15']), True)['motion'][0]
        self.assertAlmostEqual(fine, normal * .3)

    def test_stop_overrides_every_other_key_and_zoom_suspends_stick(self):
        controller = Input(); controller.evaluate(state(), True)
        release = controller.evaluate(state((255,127)), True)['motion'][2]
        result = controller.evaluate(state((255,127), ['G3']), True)
        self.assertTrue(release.is_set()); self.assertEqual(result['zoom'], 1)
        result = controller.evaluate(state((255,127), ['G1','G3','G12']), True)
        self.assertEqual(result['actions'], ['stop']); self.assertIsNone(result['motion'])
        self.assertEqual(result['zoom'], 0)

    def test_dangerous_profile_mappings_and_invalid_states_are_rejected(self):
        verify_profile(PROFILE)
        for change in ({'bindings': {'G1':'KEY_A'}}, {'macros': {'G1':[]}},
                       {'shortcuts': {'G1':['KEY_A']}}, {'slot':1}, {'stick_mode':'mouse'}):
            with self.assertRaises(ValueError): verify_profile({**PROFILE, **change})
        for stick in ([True,127], [256,127], [128], ['128',128]):
            with self.assertRaises(ValueError): State.parse(dict(kind='state',stick=stick,keys=[]))

    def test_real_socket_fragmentation_and_disconnect_clear_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'test.sock'
            server = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); server.bind(str(path)); server.listen()
            sent = threading.Event(); finish = threading.Event()
            def serve():
                with server.accept()[0] as client:
                    client.recv(100)
                    data = json.dumps(dict(kind='state',profile_id=PROFILE_ID,profile=PROFILE_NAME,
                                           stick=[147,127],keys=[],mr_state='idle')).encode()+b'\n'
                    client.sendall(data[:17]); client.sendall(data[17:]); sent.set(); finish.wait(2)
            thread = threading.Thread(target=serve); thread.start()
            subscriber = Subscription(path); subscriber.start()
            try:
                pump(lambda: subscriber.latest()[0] is not None)
                self.assertEqual(subscriber.latest()[0].stick,(147,127))
                finish.set(); thread.join(2)
                pump(lambda: subscriber.latest()[0] is None)
            finally:
                finish.set(); subscriber.close(); server.close(); thread.join(2)


class G13FlowTests(StudioFlowCase):
    def setUp(self):
        super().setUp(); self.attach(MotionCamera())
        self.current = state()
        self.app.g13.client = SimpleNamespace(latest=lambda:(self.current,''), close=lambda:None)
        self.app.g13.focused = lambda: True
        self.app.g13.enabled = True
        self.app.g13.tick()

    def tearDown(self):
        self.camera.release.set(); self.app.g13.disable(); super().tearDown()

    def test_g13_blocks_wheel_and_mouse_then_releases_wheel_when_off(self):
        self.assertTrue(self.wheel(-1)); self.assertIsNone(self.app.wheel_zoom_timer)
        self.assertEqual(self.camera.writes, [])
        self.app.manual_ready = True
        gesture = MouseGesture(); self.app.manual_drag_begin(gesture, 0, 0)
        self.assertFalse(self.app.manual_drag.active)
        self.app.g13.disable(); self.wheel(-1); self.finish()
        self.assertEqual(self.zoom_writes(), [45])

    def test_stick_uses_relative_pulse_and_release_sends_final_stop(self):
        self.current = state((255,127)); self.app.g13.tick()
        pump(self.camera.moving.is_set)
        self.current = state(); self.app.g13.tick(); self.finish()
        self.assertEqual([w[1] for w in self.camera.writes if w[0]=='send'],[0x6484,0x6484,0x6704])
        self.assertNotIn(0x6444,[w[1] for w in self.camera.writes])

    def test_g13_zoom_works_in_docked_preview_from_actual_camera_value(self):
        self.app.detached_window = None
        self.current = state(keys=['G3']); self.app.zoom.set_value(90)
        self.app.g13.tick(); self.finish()
        self.assertEqual(self.zoom_writes(), [45])

    def test_book_capture_accept_once_and_only_in_active_book_window(self):
        calls=[]
        self.app.book_window=SimpleNamespace(is_active=lambda:True,
            capture_page=lambda:calls.append('capture'),accept_pending=lambda:calls.append('accept'))
        for keys in (['G16'],['G16'],[],['G17'],['G17'],[]):
            self.current=state(keys=keys);self.app.g13.tick()
        self.assertEqual(calls,['capture','accept'])
        self.app.book_window.is_active=lambda:False
        with patch.object(self.app,'open_book') as opened:
            for keys in (['G17'],[],['G16']):
                self.current=state(keys=keys);self.app.g13.tick()
            self.assertEqual(calls,['capture','accept']);opened.assert_called_once()
        self.app.book_window=None

    def test_stop_interrupts_busy_pulse_and_disables_g13(self):
        self.current = state((255,127)); self.app.g13.tick(); pump(self.camera.moving.is_set)
        self.current = state(keys=['G22']); self.app.g13.tick(); self.finish()
        pump(lambda:not self.app.stop_pending and not self.app.busy)
        self.assertFalse(self.app.g13.active)
        self.assertTrue(self.app.g13.input.release.is_set())
        self.assertEqual(self.camera.writes[-1][1],0x6704)

    def test_actions_are_not_repeated_and_other_profile_is_inert(self):
        with patch.object(self.app,'open_gwen') as opened:
            self.current = state(keys=['G12']); self.app.g13.tick(); self.app.g13.tick()
            opened.assert_called_once()
        from dataclasses import replace
        self.current = replace(state((255,127),['G3']),profile_id='profile-1')
        self.app.g13.tick(); self.assertEqual(self.camera.writes,[])

    def test_motion_error_disables_input_and_releases_mouse(self):
        self.camera.fail_motion = True
        self.current = state((255,127)); self.app.g13.tick(); self.finish()
        self.assertFalse(self.app.g13.active)
        self.assertTrue(self.app.g13.input.release.is_set())

    def test_enable_validates_profile_and_clears_old_mouse_commands(self):
        self.app.g13.disable(); self.wheel(-2)
        with (patch('tiny2.g13_control.request',side_effect=[{'profile':PROFILE},{'ok':True}]) as request,
              patch('tiny2.g13_control.Subscription') as subscription):
            self.app.g13.enable(); self.finish()
            self.assertTrue(self.app.g13.enabled)
            self.assertIsNone(self.app.wheel_zoom.pending)
            self.assertEqual(self.zoom_writes(),[])
            self.assertEqual(request.call_args.args[0]['cmd'],'switch_profile')
            subscription.return_value.start.assert_called_once()


if __name__ == '__main__': unittest.main()
