from typing import Dict, Optional, Union, List

from fastapi.responses import Response, JSONResponse, PlainTextResponse

from config import *
from renderers import Renderer
from profiles import profiles
from utils import templates


class VocPrezProfilesRenderer(Renderer):
    profiles = {"profiles": profiles}
    default_profile_token = "profiles"

    def __init__(self, request: object, instance_uri: str) -> None:
        super().__init__(
            request,
            VocPrezProfilesRenderer.profiles,
            VocPrezProfilesRenderer.default_profile_token,
            instance_uri,
        )

    def set_profiles(self, profile_list: List[Dict]) -> None:
        self.profile_list = profile_list

    def _render_profiles_html(
        self, template_context: Union[Dict, None]
    ) -> templates.TemplateResponse:
        """Renders the HTML representation of the profiles profile for a dataset"""
        _template_context = {
            "request": self.request,
            "uri": self.instance_uri,
            "profiles": self.profile_list,
        }
        if template_context is not None:
            _template_context.update(template_context)
        return templates.TemplateResponse(
            "vocprez/vocprez_profiles.html",
            context=_template_context,
            headers=self.headers,
        )

    def _render_profiles_json(self) -> Response:
        """Renders the JSON representation of the profiles profile for a dataset"""
        return JSONResponse(content=self.profile_list)

    def _render_profiles(self, template_context: Union[Dict, None]):
        """Renders the profiles profile for a dataset"""
        if self.mediatype == "text/html":
            return self._render_profiles_html(template_context)
        else:  # only other format is JSON
            return self._render_profiles_json()

    def render(
        self, template_context: Optional[Dict] = None
    ) -> Union[
        PlainTextResponse, templates.TemplateResponse, Response, JSONResponse, None
    ]:
        if self.error is not None:
            return PlainTextResponse(self.error, status_code=400)
        elif self.profile == "alt":
            return self._render_alt(template_context)
        elif self.profile == "profiles":
            return self._render_profiles(template_context)
        else:
            return None
