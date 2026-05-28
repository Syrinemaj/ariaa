class ApprovalRequiredError(Exception):
    pass


def assert_approval_for_real_execution(dry_run: bool, approval_granted: bool) -> None:
    if dry_run:
        return
    if not approval_granted:
        raise ApprovalRequiredError("Real execution requires approval.")
