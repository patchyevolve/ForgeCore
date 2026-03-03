from enum import Enum, auto

class State(Enum):
	IDLE = auto()
	PLANNING = auto()
	CRITIC_REVIEW = auto()
	PATCH_READY = auto()
	APPLYING = auto()
	COMPILING = auto()
	ERROR_CLASSIFY = auto()
	REFINEMENT = auto()
	FINAL_CRITIC = auto()
	MODULE_INTEGRITY_CHECK = auto()
	COMMIT = auto()
	ABORT = auto()


class InvalidTransitionError(Exception):
	pass

class StateMachine:
	def __init__(self, logger):
		self.current_state = State.IDLE
		self.logger = logger

		self.valid_transitions = {
			State.IDLE:				{State.PLANNING},

			State.PLANNING:			{State.CRITIC_REVIEW, State.ABORT},
			
			State.CRITIC_REVIEW:	{State.PATCH_READY, State.ABORT},

			State.PATCH_READY:		{State.APPLYING, State.ABORT},
			
			State.APPLYING:			{State.COMPILING, State.ABORT},
			
			State.COMPILING:		{State.FINAL_CRITIC, State.ERROR_CLASSIFY},

			State.FINAL_CRITIC:		{State.MODULE_INTEGRITY_CHECK, State.ABORT},
			
			State.MODULE_INTEGRITY_CHECK: {State.COMMIT, State.ABORT},
			
			State.ERROR_CLASSIFY:	{State.REFINEMENT, State.ABORT},
			
			State.REFINEMENT:		{State.PLANNING, State.ABORT},
			
			State.COMMIT:			{State.IDLE},
			
			State.ABORT:			{State.IDLE},
		}

	def transition_to(self, new_state: State):
		if new_state not in self.valid_transitions[self.current_state]:
			raise InvalidTransitionError(
				f"Invalid transition from {self.current_state.name} "
				f"to{new_state.name}"
			)

		old_state = self.current_state
		self.current_state = new_state

		self.logger.log_event(
			state= new_state.name,
			event= "STATE_TRANSITION",
			details={
				"from": old_state.name,
				"to": new_state.name
			}
		)

	def get_state(self):
		return self.current_state