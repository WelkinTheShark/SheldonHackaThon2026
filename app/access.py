"""Who is looking at the page, and which developers' calls and roasts they may see.

Every developer token carries an access level:
  self  sees only their own calls and roasts
  team  sees everyone on the same team
  all   sees everything and can manage users, settings and the demo
The shared gateway token signs in as Admin with all access, so the team can never be locked out.
"""
import hmac
from dataclasses import dataclass

from fastapi import HTTPException, Request

from . import config, store

LEVELS = ("self", "team", "all")
PAGE_HEADER = "x-cavedawg-token"
ADMIN_NAME = "Admin"


@dataclass
class Viewer:
    id: int | None
    name: str
    team: str
    access: str

    @property
    def can_manage(self) -> bool:
        return self.access == "all"

    def public(self) -> dict:
        return {
            "id": self.id, "name": self.name, "team": self.team,
            "access": self.access, "can_manage": self.can_manage,
        }


def _supplied(request: Request) -> str:
    # Claude Code's roast script sends x-api-key. The page sends its own header.
    bearer = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    return request.headers.get("x-api-key") or bearer or request.headers.get(PAGE_HEADER, "")


def viewer_for(token: str) -> Viewer | None:
    if not token:
        return None
    # A developer token (Claude Code and the page) or a page session from a password login.
    developer = store.developer_by_token(token) or store.developer_by_session(token)
    if developer:
        return Viewer(developer["id"], developer["name"], developer["team"], developer["access"])
    shared = config.settings.gateway_token
    if shared and hmac.compare_digest(token.encode(), shared.encode()):
        return Viewer(None, ADMIN_NAME, "", "all")
    return None


def page_token(request: Request) -> str:
    return _supplied(request).strip()


def require_viewer(request: Request) -> Viewer:
    viewer = viewer_for(_supplied(request).strip())
    if viewer is None:
        raise HTTPException(401, "Sign in to CaveDawg.")
    return viewer


def require_manager(request: Request) -> Viewer:
    viewer = require_viewer(request)
    if not viewer.can_manage:
        raise HTTPException(403, "Only users with all access can change this.")
    return viewer


def scope(viewer: Viewer) -> set | None:
    """Developer IDs this viewer may see. None means everything, including unattributed calls."""
    if viewer.access == "all":
        return None
    visible = {viewer.id}
    if viewer.access == "team" and viewer.team:
        visible |= {d["id"] for d in store.list_developers() if d["team"] == viewer.team}
    return visible


def can_see(viewer: Viewer, developer_id: int | None) -> bool:
    visible = scope(viewer)
    return visible is None or developer_id in visible
