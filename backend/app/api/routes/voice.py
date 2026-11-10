"""Voice Assistant routes (/api/v1/voice/...).

Expansion Feature 3. Authorization follows the Gate 2 review
§4.2 inheritance contract and the feature's own standard — BOTH
depths, deliberately: routes gate on the ``Permission`` enum
(reads: ``read_system_data``; session/audio/transcript writes:
``write_system_data``; transcription and synthesis:
``execute_tools``; interpretation: ``submit_tasks``; confirmation
and rejection: ``approve_actions``), and the service layer
additionally refuses every non-owner principal, because the
voice channel acts with the owner's authority and holds the
owner's private audio and transcripts.

Confirmation exists ONLY here, as an authenticated owner API
call. No route accepts a transcript as a confirmation, and no
voice input of any phrasing can confirm a command — a spoken
"approve" is interpreted as a new command and changes nothing.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from ...core.application import Application
from ...permissions.models import Permission, Principal
from ..dependencies import (
    correlation_id, get_application, get_principal, require_permission,
)
from ..schemas.common import ok, page
from ..schemas.voice import (
    ManualTranscriptIn, VoiceSessionCreateIn, VoiceSessionUpdateIn,
)

router = APIRouter(tags=["voice"])

READ = require_permission(Permission.READ_SYSTEM_DATA)
WRITE = require_permission(Permission.WRITE_SYSTEM_DATA)
EXECUTE = require_permission(Permission.EXECUTE_TOOLS)
SUBMIT = require_permission(Permission.SUBMIT_TASKS)
APPROVE = require_permission(Permission.APPROVE_ACTIONS)


def _svc(application: Application):
    return application.voice


# -------------------------------------------------------------- status
@router.get("/voice/status")
async def voice_status(request: Request,
                       application: Application = Depends(get_application),
                       _: Principal = Depends(READ)):
    return ok(await _svc(application).status(), correlation_id(request))


@router.get("/voice/providers")
async def voice_providers(request: Request,
                          application: Application = Depends(get_application),
                          _: Principal = Depends(READ)):
    return ok(await _svc(application).providers_status(),
              correlation_id(request))


# ------------------------------------------------------------- sessions
@router.post("/voice/sessions", status_code=201)
async def create_session(body: VoiceSessionCreateIn, request: Request,
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(WRITE)):
    return ok(_svc(application).create_session(principal, body.model_dump()),
              correlation_id(request))


@router.get("/voice/sessions")
async def list_sessions(request: Request,
                        application: Application = Depends(get_application),
                        principal: Principal = Depends(READ),
                        limit: int = Query(default=100, ge=1, le=500),
                        offset: int = Query(default=0, ge=0)):
    rows, total = _svc(application).list_sessions(
        principal, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.get("/voice/sessions/{session_id}")
async def get_session(session_id: str, request: Request,
                      application: Application = Depends(get_application),
                      principal: Principal = Depends(READ)):
    return ok(_svc(application).get_session(principal, session_id),
              correlation_id(request))


@router.patch("/voice/sessions/{session_id}")
async def update_session(session_id: str, body: VoiceSessionUpdateIn,
                         request: Request,
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(WRITE)):
    patch = body.model_dump(exclude_unset=True)
    return ok(_svc(application).update_session(principal, session_id, patch),
              correlation_id(request))


@router.post("/voice/sessions/{session_id}/close")
async def close_session(session_id: str, request: Request,
                        application: Application = Depends(get_application),
                        principal: Principal = Depends(WRITE)):
    return ok(_svc(application).close_session(principal, session_id),
              correlation_id(request))


@router.delete("/voice/sessions/{session_id}")
async def delete_session(session_id: str, request: Request,
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(WRITE)):
    return ok(_svc(application).delete_session(principal, session_id),
              correlation_id(request))


# ---------------------------------------------------------------- audio
@router.post("/voice/sessions/{session_id}/audio", status_code=201)
async def upload_audio(session_id: str, request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(WRITE),
                       filename: str = Query(default="recording.wav")):
    """Raw-body audio intake: the request body IS the audio, its
    Content-Type header the media type, ``filename`` a query
    parameter. No multipart dependency is added to the stack for
    one endpoint (the F02 no-new-dependency precedent)."""
    data = await request.body()
    result = _svc(application).store_audio(
        principal, session_id, filename=filename,
        content_type=request.headers.get("content-type", ""), data=data)
    return ok(result, correlation_id(request))


@router.get("/voice/sessions/{session_id}/audio")
async def list_audio(session_id: str, request: Request,
                     application: Application = Depends(get_application),
                     principal: Principal = Depends(READ),
                     limit: int = Query(default=100, ge=1, le=500),
                     offset: int = Query(default=0, ge=0)):
    rows, total = _svc(application).list_audio(
        principal, session_id, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.get("/voice/audio/{audio_id}/content")
async def audio_content(audio_id: str, request: Request,
                        application: Application = Depends(get_application),
                        principal: Principal = Depends(READ)):
    _row, data, content_type = _svc(application).read_audio(
        principal, audio_id)
    return Response(content=data,
                    media_type=content_type or "application/octet-stream")


@router.delete("/voice/audio/{audio_id}")
async def delete_audio(audio_id: str, request: Request,
                       application: Application = Depends(get_application),
                       principal: Principal = Depends(WRITE)):
    return ok(_svc(application).delete_audio(principal, audio_id),
              correlation_id(request))


@router.post("/voice/audio/{audio_id}/transcribe")
async def transcribe_audio(audio_id: str, request: Request,
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(EXECUTE)):
    result = await _svc(application).transcribe(
        principal, audio_id, correlation_id=correlation_id(request))
    return ok(result, correlation_id(request))


# ----------------------------------------------------------- transcripts
@router.post("/voice/sessions/{session_id}/transcripts/manual",
             status_code=201)
async def manual_transcript(session_id: str, body: ManualTranscriptIn,
                            request: Request,
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(WRITE)):
    result = _svc(application).create_manual_transcript(
        principal, session_id, body.text)
    return ok(result, correlation_id(request))


@router.get("/voice/sessions/{session_id}/transcripts")
async def list_transcripts(session_id: str, request: Request,
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(READ),
                           limit: int = Query(default=100, ge=1, le=500),
                           offset: int = Query(default=0, ge=0)):
    rows, total = _svc(application).list_transcripts(
        principal, session_id, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.delete("/voice/transcripts/{transcript_id}")
async def delete_transcript(transcript_id: str, request: Request,
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(WRITE)):
    return ok(_svc(application).delete_transcript(principal, transcript_id),
              correlation_id(request))


@router.post("/voice/transcripts/{transcript_id}/interpret")
async def interpret_transcript(transcript_id: str, request: Request,
                               application: Application = Depends(get_application),
                               principal: Principal = Depends(SUBMIT)):
    result = await _svc(application).interpret(
        principal, transcript_id, correlation_id=correlation_id(request))
    return ok(result, correlation_id(request))


# -------------------------------------------------------------- commands
@router.get("/voice/sessions/{session_id}/commands")
async def list_commands(session_id: str, request: Request,
                        application: Application = Depends(get_application),
                        principal: Principal = Depends(READ),
                        status: str | None = Query(default=None),
                        limit: int = Query(default=100, ge=1, le=500),
                        offset: int = Query(default=0, ge=0)):
    rows, total = _svc(application).list_commands(
        principal, session_id, status=status, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.get("/voice/commands/{command_id}")
async def get_command(command_id: str, request: Request,
                      application: Application = Depends(get_application),
                      principal: Principal = Depends(READ)):
    return ok(_svc(application).get_command(principal, command_id),
              correlation_id(request))


@router.post("/voice/commands/{command_id}/confirm")
async def confirm_command(command_id: str, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(APPROVE)):
    result = await _svc(application).confirm(
        principal, command_id, correlation_id=correlation_id(request))
    return ok(result, correlation_id(request))


@router.post("/voice/commands/{command_id}/reject")
async def reject_command(command_id: str, request: Request,
                         application: Application = Depends(get_application),
                         principal: Principal = Depends(APPROVE)):
    return ok(_svc(application).reject(principal, command_id),
              correlation_id(request))


@router.post("/voice/commands/{command_id}/synthesize")
async def synthesize_command(command_id: str, request: Request,
                             application: Application = Depends(get_application),
                             principal: Principal = Depends(EXECUTE)):
    result = await _svc(application).synthesize(principal, command_id)
    return ok(result, correlation_id(request))
