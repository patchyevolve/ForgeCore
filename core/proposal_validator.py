class ProposalValidationError(Exception):
    pass

class PlannerProposalValidator:
    
    ALLOWED_RISK_LEVELS = {"low","medium","high"}
    ALLOWED_OPERATIONS = {"overwrite"}

    REQUIRED_TOP_FIELDS = {
        "task_id",
        "summary",
        "risk_level",
        "requires_tier1",
        "requires_crypto_flag",
        "patches"
        }

    REQUIRED_PATCH_FIELDS = {
        "file",
        "operation",
        "justification",
        "expected_effect",
        "content"
    }

    def validate(self, proposal: dict):
        self._validate_top_level(proposal)
        self._validate_patches(proposal["patches"])

    def _validate_top_level(self, proposal):
        if not isinstance(proposal, dict):
            raise ProposalValidationError("Proposal must be a dictionary.")

        missing = self.REQUIRED_TOP_FIELDS - proposal.keys()
        if missing:
            raise ProposalValidationError(f"Missing top-level fields: {missing}")

        if proposal["risk_level"] not in self.ALLOWED_RISK_LEVELS:
            raise ProposalValidationError("Invalid risk_level value.")

        if not isinstance(proposal["requires_tier1"], bool):
            raise ProposalValidationError("requires_tier1 must be boolean.")

        if not isinstance(proposal["requires_crypto_flag"], bool):
            raise ProposalValidationError("requires_crypto_flag must be boolean.")

        if not isinstance(proposal["patches"], list):
            raise ProposalValidationError("patches must be a list.")

    def _validate_patches(self, patches):
        seen_files = set()

        for patch in patches:
            if not isinstance(patch, dict):
                raise ProposalValidationError("Each patch must be a dictionary.")

            missing = self.REQUIRED_PATCH_FIELDS - patch.keys()
            if missing:
                raise ProposalValidationError(f"Missing patch fields: {missing}")

            if patch["operation"] not in self.ALLOWED_OPERATIONS:
                raise ProposalValidationError("Invalid operation type.")

            if not isinstance(patch["file"], str):
                raise ProposalValidationError("Patch file must be string.")

            if patch["file"] in seen_files:
                raise ProposalValidationError("Duplicate file in patches.")

            seen_files.add(patch["file"])

            if not isinstance(patch["content"], str):
                raise ProposalValidationError("Patch content must be string.")