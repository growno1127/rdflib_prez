import io

from fastapi import APIRouter
from rdflib import Namespace, Graph
from starlette.background import BackgroundTask
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import StreamingResponse

from prez.models.profiles_and_mediatypes import ProfilesMediatypesInfo
from prez.renderers.renderer import return_annotated_rdf
from prez.sparql.methods import sparql

PREZ = Namespace("https://prez.dev/")

router = APIRouter(tags=["SPARQL"])


@router.api_route("/sparql", methods=["GET"])
async def sparql_endpoint(request: Request):
    request_mediatype = request.headers.get("accept").split(",")[
        0
    ]  # can't default the MT where not provided as it could be
    # graph (CONSTRUCT like queries) or tabular (SELECT queries)

    # Intercept "+anot" mediatypes
    if "anot+" in request_mediatype:
        prof_and_mt_info = ProfilesMediatypesInfo(
            request=request, classes=frozenset([PREZ.SPARQLQuery])
        )
        non_anot_mediatype = request_mediatype.replace("anot+", "")
        request._headers = Headers({**request.headers, "accept": non_anot_mediatype})
        response = await sparql(request)
        await response.aread()
        g = Graph()
        g.parse(data=response.text, format=non_anot_mediatype)
        graph = await return_annotated_rdf(g, prof_and_mt_info.profile)
        content = io.BytesIO(
            graph.serialize(format=non_anot_mediatype, encoding="utf-8")
        )
        return StreamingResponse(
            content=content,
            media_type=non_anot_mediatype,
            headers=prof_and_mt_info.profile_headers,
        )
    else:
        response = await sparql(request)
        return StreamingResponse(
            response.aiter_raw(),
            status_code=response.status_code,
            headers=dict(response.headers),
            background=BackgroundTask(response.aclose),
        )
