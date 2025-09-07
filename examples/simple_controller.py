#!/usr/bin/env python
import koruza


class ExampleController(koruza.Application):
    # This is the application identifier so that messages may be directed to
    # this specific application on the bus.
    application_id: str = 'example_controller'
    # Current state.
    state: str = 'idle'
    # Initial position.
    initial_position: dict = None

    def on_command(self, bus: koruza.Bus, command: dict, state: dict) -> None:
        if command['command'] == 'start':
            print('got start command')
            self.state = 'go'
            self.initial_position = state.get('motors', {}).get('motor')
        elif command['command'] == 'stop':
            print('got stop command')
            self.state = 'idle'

            # Reset to initial position if known.
            if self.initial_position:
                print('moving to initial position')
                bus.command(
                    'motor_move',
                    next_x=self.initial_position['current_x'],
                    next_y=self.initial_position['current_y'],
                    next_f=self.initial_position['current_f'],
                )

    def on_idle(self, bus: koruza.Bus, state: dict) -> None:
        if self.state == 'go':
            if not state.get('sfp') or not state.get('motors'):
                # Do nothing until we have known last state from SFP and motor drivers.
                return

            # Get last known state for the first SFP module.
            sfp = list(state['sfp']['sfp'].values())[0] #simplified in python 3
            # Get last known motor driver state.
            motor = state['motors']['motor']

            # Request the motor to move to 0 on X axis.
            if motor['current_x'] != 0 and motor['next_x'] != 0:
                print('requesting the motor to reset x axis to 0')
                bus.command('motor_move', next_x=0)
        elif self.state == 'idle':
            pass


ExampleController().start()
