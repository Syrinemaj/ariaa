"""ARIA-EVAL: sandbox environment workaround, NOT a production practice.

This specific dev sandbox's system clock has been observed to drift several
hours behind real UTC (verified empirically: local clock vs. the real AWS
server time read out of a rejected SigV4 signature). AWS rejects any
request signed with a timestamp more than 5-15 minutes off its own clock,
so every Bedrock/STS call fails with "Signature expired" until this is
corrected. `w32tm`/`Set-Date` both require admin rights this sandbox
doesn't have — see the conversation for that dead end — so the fix lives
here instead: measure the live offset via one throwaway (free, always-
rejected) STS call, then monkeypatch botocore's signing clock source for
the rest of the process.

A correctly NTP-synced machine needs none of this — apply_clock_fix() is a
no-op (returns timedelta(0), patches nothing) if the offset is already
under a minute.
"""
from __future__ import annotations

import datetime
import re

import boto3
from botocore.exceptions import ClientError
import botocore.auth as botocore_auth
from botocore.compat import get_current_datetime as _real_get_current_datetime

_SERVER_TIME_RE = re.compile(r"\((\d{8}T\d{6}Z) - ")


def measure_offset(region: str = "eu-west-2") -> datetime.timedelta:
    """One throwaway STS call whose only purpose is to read AWS's real
    server time out of the rejection error message (a correctly-signed
    call wouldn't expose it). No cost — STS calls are free, and this one
    is expected to fail."""
    sts = boto3.client("sts", region_name=region)
    local_now = datetime.datetime.now(datetime.timezone.utc)
    try:
        sts.get_caller_identity()
        return datetime.timedelta(0)  # clock was already fine, signature accepted
    except ClientError as e:
        msg = e.response.get("Error", {}).get("Message", "")
        m = _SERVER_TIME_RE.search(msg)
        if not m:
            # Some other auth failure (bad credentials, etc.) — not our problem
            # to fix here, let the caller's next real call surface it properly.
            return datetime.timedelta(0)
        server_time = datetime.datetime.strptime(
            m.group(1), "%Y%m%dT%H%M%SZ"
        ).replace(tzinfo=datetime.timezone.utc)
        return server_time - local_now


def apply_clock_fix(region: str = "eu-west-2") -> datetime.timedelta:
    """Idempotent-ish: re-measures and re-patches each call (cheap, and
    correct if the drift itself drifts across a long run). Returns the
    offset applied — timedelta(0) means no correction was needed."""
    offset = measure_offset(region)
    if abs(offset.total_seconds()) < 60:
        return offset

    def _corrected_get_current_datetime(remove_tzinfo: bool = True):
        dt = _real_get_current_datetime(remove_tzinfo=False) + offset
        return dt.replace(tzinfo=None) if remove_tzinfo else dt

    botocore_auth.get_current_datetime = _corrected_get_current_datetime
    return offset
