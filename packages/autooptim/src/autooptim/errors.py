"""Error types for the AutoOptim framework."""


class AutoOptimError(Exception):
    """Base error for all AutoOptim errors."""


class MutationError(AutoOptimError):
    """Raised when a mutation fails validation or application."""


class PreflightError(MutationError):
    """Raised when pre-flight checks fail after applying changes."""


class ProposerError(AutoOptimError):
    """Raised when the proposer fails to generate a valid plan."""


class EvaluatorError(AutoOptimError):
    """Raised when evaluation fails."""


class ConfigError(AutoOptimError):
    """Raised when configuration is invalid."""


class GitError(AutoOptimError):
    """Raised when a git operation fails."""
