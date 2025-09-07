import pynng
import select
import json
import traceback
import time
    

class Bus(object):
    def __init__(self):
        self._socket = pynng.Req0() #updated to use new pynng API
        self._socket.connect('ipc:///tmp/koruza-command.ipc')

    def command(self, command: str, **data: dict) -> dict:
        data.update({
            'type': 'command',
            'command': command,
        })

        self._socket.send(json.dumps(data).encode())
        try:
            return json.loads(self._socket.recv().decode())
        except ValueError:
            return None


class Application(object):
    application_id = None
    needs_remote = False

    def __init__(self):
        self._topic = f'application.{self.application_id}' #updated to use f-strings
        self.config = {}

    def start(self):    
        # Establish IPC connections.
        publish = pynng.Sub0()
        publish.connect('ipc:///tmp/koruza-publish.ipc')
        publish.subscribe(b'status')
        publish.subscribe(self._topic.encode())
        publish_fd = publish.recv_fd()

        command_bus = Bus()
        self._command_bus = command_bus

        poll = select.poll()
        poll.register(publish_fd, select.POLLIN)

        last_state = {}
        last_remote_state = {}
        last_remote_ip_check = 0

        remote_ip = None
        remote_publish = None
        remote_publish_fd = None

        # Get initial configuration.
        self.config = command_bus.command('get_status')['config']

        while True:
            now = time.time()

            # Check for incoming updates, block for at most 100 ms.
            for fd, event in poll.poll(100):
                if fd == publish_fd:
                    socket = publish
                    remote = False
                elif fd == remote_publish_fd:
                    socket = remote_publish
                    remote = True

                while True:
                    try:
                        msg = socket.recv(flags=pynng.Flags.NONBLOCK).decode() #updated to use new pynng API
                        topic, payload = msg.split('@', 1) 
                    except AssertionError:
                        break

                    try:
                        data = json.loads(payload)
                    except ValueError:
                        continue

                    try:
                        if topic == self._topic:
                            if data['type'] == 'command' and not remote:
                                self.on_command(command_bus, data, last_state, last_remote_state)
                            elif data['type'] == 'app_status':
                                state = last_remote_state if remote else last_state
                                state.setdefault('app_status', {}).update(data['value'])

                                for key in data['value']:
                                    state.setdefault('_age', {}).setdefault('app_status', {})[key] = now
                        elif topic == 'status':
                            if remote:
                                last_remote_state[data['type']] = data
                                last_remote_state.setdefault('_age', {})[data['type']] = now
                                self.on_remote_status_update(command_bus, data)
                            else:
                                last_state[data['type']] = data
                                last_state.setdefault('_age', {})[data['type']] = now
                                self.on_status_update(command_bus, data)
                    except:
                        traceback.print_exc()

            # Run local processing.
            self.on_idle(command_bus, last_state, last_remote_state)

            # Check for remote IP change.
            if self.needs_remote and now - last_remote_ip_check > 30:
                # Request configuration to discover the remote IP.
                status = command_bus.command('get_status')
                self.config = status['config']
                next_remote_ip = self.config.get('remote_ip', None)
                last_remote_ip_check = now
                if not next_remote_ip or next_remote_ip.startswith('127.') or next_remote_ip == remote_ip:
                    continue
                else:
                    remote_ip = next_remote_ip

                if remote_publish is not None:
                    remote_publish.close()
                    poll.unregister(remote_publish_fd)
                    remote_publish_fd = None

                remote_publish = nnpy.Socket(nnpy.AF_SP, nnpy.SUB)
                remote_publish.connect(f'tcp://{str(next_remote_ip)}:7100') #updated to use f-strings 
                remote_publish.setsockopt(nnpy.SUB, nnpy.SUB_SUBSCRIBE, 'status')
                remote_publish.setsockopt(nnpy.SUB, nnpy.SUB_SUBSCRIBE, self._topic)
                remote_publish_fd = remote_publish.getsockopt(nnpy.SOL_SOCKET, nnpy.RCVFD)
                poll.register(remote_publish_fd, select.POLLIN)

    def publish(self, data: dict) -> None:
        self._command_bus.command(
            'call_application',
            application_id=self.application_id,
            payload={
                'type': 'app_status',
                'value': data,
            }
        )

    def get_age(self, state: dict, *path: str) -> float:
        age = state.get('_age', {})

        for atom in path:
            age = age.get(atom, None)
            if age is None:
                return 0

            if isinstance(age, dict):
                continue
            else:
                return time.time() - age

    def on_idle(self, bus: Bus, state: dict, remote_state: dict) -> None:
        pass

    def on_command(self, bus: Bus, command: dict, state: dict, remote_state: dict) -> None:
        pass

    def on_status_update(self, bus: Bus, update: dict) -> None:
        pass

    def on_remote_status_update(self, bus: Bus, update: dict) -> None:
        pass
