import json
import os
from datetime import datetime 

class Logger:
	def __init__(self, log_directory="logs"):
		os.makedirs(log_directory, exist_ok=True)

		timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
		self.log_path = os.path.join(log_directory, f"session_{timestamp}.json")

		self._initialize_log_file()

	def _initialize_log_file(self):
		with open(self.log_path, "w") as f:
			json.dump([], f)

	def log_event(self, state, event, details=None):
		if details is None:
			details = {}

		entry = {
			"timestamp": datetime.now().isoformat(),
			"state": state,
			"event": event,
			"details": details
		}

		with open(self.log_path, "r+") as f:
			log_data = json.load(f)
			log_data.append(entry)
			f.seek(0)
			json.dump(log_data, f, indent=4)
			f.truncate()

