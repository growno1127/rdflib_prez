import logging
from functools import lru_cache
from pathlib import Path
from typing import FrozenSet

from rdflib import Graph, URIRef, Namespace
from rdflib.namespace import GEO, DCAT, SKOS
from starlette.requests import Request
from starlette.responses import Response

from prez.models import SpatialItem, VocabItem, CatalogItem
from prez.cache import profiles_graph_cache
from prez.services.sparql_queries import (
    select_profile_mediatype,
    generate_item_construct,
)
from prez.services.sparql_utils import (
    sparql_construct_non_async,
)
from prez.renderers.renderer import return_from_graph
from prez.services.connegp_service import get_requested_profile_and_mediatype


def create_profiles_graph(ENABLED_PREZS) -> Graph:
    if (
        len(profiles_graph_cache) > 0
    ):  # pytest imports app.py multiple times, so this is needed. Not sure why cache is
        # not cleared between calls
        return
    for f in Path(__file__).parent.glob("*.ttl"):
        profiles_graph_cache.parse(f)
    logging.info("Loaded local profiles")

    remote_profiles_query = """
        PREFIX dcat: <http://www.w3.org/ns/dcat#>
        PREFIX geo: <http://www.opengis.net/ont/geosparql#>
        PREFIX prof: <http://www.w3.org/ns/dx/prof/>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

        CONSTRUCT {?s ?p ?o .
                    ?o ?p2 ?o2 .
                    ?o2 ?p3 ?o3 .
                    ?class ?cp ?co}
        WHERE {?s a prof:Profile ;
                      ?p ?o
          OPTIONAL {?o ?p2 ?o2
            FILTER(ISBLANK(?o))
            OPTIONAL {?o2 ?p3 ?o3
            FILTER(ISBLANK(?o2))}
          }
          OPTIONAL {
            ?class rdfs:subClassOf dcat:Resource ;
                ?cp ?co .
          }
          OPTIONAL {
            ?class rdfs:subClassOf geo:Feature ;
                ?cp ?co .
          }
          OPTIONAL {
            ?class rdfs:subClassOf skos:Concept ;
                ?cp ?co .
          }
        }
        """

    for p in ENABLED_PREZS:
        r = sparql_construct_non_async(remote_profiles_query, p)
        if r[0]:
            profiles_graph_cache.__add__(r[1])
            logging.info(f"Also using remote profiles for {p}")


@lru_cache(maxsize=128)
def get_profiles_and_mediatypes(
    classes: FrozenSet[URIRef],
    requested_profile: URIRef = None,
    requested_mediatype: URIRef = None,
):
    query = select_profile_mediatype(classes, requested_profile, requested_mediatype)
    response = profiles_graph_cache.query(query)
    if len(response.bindings[0]) == 0:
        raise ValueError(
            f"No profiles and or mediatypes could be found to render the resource. The resource class(es) searched for "
            f"were: {', '.join(klass for klass in classes)}"
        )
    top_result = response.bindings[0]
    profile, mediatype, selected_class = (
        top_result["profile"],
        top_result["format"],
        top_result["class"],
    )
    profile_headers, avail_profile_uris = generate_profiles_headers(
        selected_class, response, profile, mediatype
    )
    return profile, mediatype, selected_class, profile_headers, avail_profile_uris


def generate_profiles_headers(selected_class, response, profile, mediatype):
    headers = {
        "Access-Control-Allow-Origin": "*",
    }
    if str(mediatype) == "text/anot+turtle":
        headers["Content-Type"] = "text/turtle"
        # TODO does something else need to be returned? the front end knows what it requested - if HTML was requested,
        #  and RDF is returned, it will know to render it as HTML
    else:
        headers["Content-Type"] = mediatype
    avail_profiles = set(
        (i["token"], i["profile"], i["title"]) for i in response.bindings
    )
    avail_profiles_headers = ", ".join(
        [
            f'<http://www.w3.org/ns/dx/prof/Profile>; rel="type"; title="{i[2]}"; token="{i[0]}"; anchor=<{i[1]}>'
            for i in avail_profiles
        ]
    )
    avail_mediatypes_headers = ", ".join(
        [
            f"""<{selected_class}?_profile={i["token"]}&_mediatype={i["format"]}>; \
rel="{"self" if i["def_profile"] and i["def_format"] else "alternate"}"; type="{i["format"]}"; profile="{i["profile"]}"\
"""
            for i in response.bindings
        ]
    )
    headers["Link"] = ", ".join(
        [
            f'<{profile}>; rel="profile"',
            avail_profiles_headers,
            avail_mediatypes_headers,
        ]
    )
    avail_profile_uris = [i[1] for i in avail_profiles]
    return headers, avail_profile_uris


async def prez_profiles(request: Request, prez_type) -> Response:
    prez_classes = {
        "SpacePrez": frozenset([GEO.Feature, GEO.FeatureCollection, DCAT.Dataset]),
        "VocPrez": frozenset([SKOS.Concept, SKOS.ConceptScheme, SKOS.Collection]),
        "CatPrez": frozenset([DCAT.Catalog, DCAT.Resource]),
    }
    prez_items = {
        "SpacePrez": SpatialItem,
        "VocPrez": VocabItem,
        "CatPrez": CatalogItem,
    }
    req_profiles, req_mediatypes = get_requested_profile_and_mediatype(request)
    (
        profile,
        mediatype,
        selected_class,
        profile_headers,
        avail_profile_uris,
    ) = get_profiles_and_mediatypes(
        prez_classes[prez_type], req_profiles, req_mediatypes
    )
    items = [
        prez_items[prez_type](uri=uri, url_path=str(request.url.path))
        for uri in avail_profile_uris
    ]
    queries = [
        generate_item_construct(profile, URIRef("http://kurrawong.net/profile/prez"))
        for profile in items
    ]
    g = Graph(bind_namespaces="rdflib")
    g.bind("altr-ext", Namespace("http://www.w3.org/ns/dx/conneg/altr-ext#"))
    for q in queries:
        g += profiles_graph_cache.query(q)
    return await return_from_graph(g, mediatype, profile, profile_headers, prez_type)
