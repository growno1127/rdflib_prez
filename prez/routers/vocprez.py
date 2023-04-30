import logging
from typing import Optional

from fastapi import APIRouter, Request
from rdflib import URIRef
from starlette.responses import PlainTextResponse

from prez.models.profiles_and_mediatypes import ProfilesMediatypesInfo
from prez.models.vocprez_item import VocabItem
from prez.models.vocprez_listings import VocabMembers
from prez.renderers.renderer import return_from_queries, return_profiles
from prez.sparql.objects_listings import (
    generate_listing_construct,
    generate_listing_count_construct,
    generate_item_construct,
)

router = APIRouter(tags=["VocPrez"])

log = logging.getLogger(__name__)


@router.get("/v", summary="VocPrez Home")
async def vocprez_home():
    return PlainTextResponse("VocPrez Home")


@router.get("/v/collection", summary="List Collections")
@router.get("/v/scheme", summary="List ConceptSchemes")
@router.get("/v/vocab", summary="List Vocabularies")
async def schemes_endpoint(
    request: Request,
    page: int = 1,
    per_page: int = 20,
):
    """Returns a list of VocPrez skos:ConceptSchemes in the necessary profile & mediatype"""
    vocprez_members = VocabMembers(url_path=str(request.url.path))
    prof_and_mt_info = ProfilesMediatypesInfo(
        request=request, classes=vocprez_members.classes
    )
    vocprez_members.selected_class = prof_and_mt_info.selected_class
    if prof_and_mt_info.profile == URIRef(
        "http://www.w3.org/ns/dx/conneg/altr-ext#alt-profile"
    ):
        return await return_profiles(
            classes=frozenset(vocprez_members.selected_class),
            prez_type="VocPrez",
            prof_and_mt_info=prof_and_mt_info,
        )
    list_query, predicates_for_link_addition = generate_listing_construct(
        vocprez_members, prof_and_mt_info.profile, page, per_page
    )
    count_query = generate_listing_count_construct(vocprez_members)
    return await return_from_queries(
        [list_query, count_query],
        prof_and_mt_info.mediatype,
        prof_and_mt_info.profile,
        prof_and_mt_info.profile_headers,
        "VocPrez",
        predicates_for_link_addition,
    )


@router.get("/v/vocab/{scheme_curie}", summary="Get ConceptScheme")
@router.get("/v/scheme/{scheme_curie}", summary="Get ConceptScheme")
async def vocprez_scheme(request: Request, scheme_curie: str):
    return await item_endpoint(request)


@router.get("/v/collection/{collection_curie}", summary="Get Collection")
async def vocprez_collection(request: Request, collection_curie: str):
    return await item_endpoint(request)


@router.get("/v/collection/{collection_curie}/{concept_curie}", summary="Get Concept")
async def vocprez_collection_concept(
    request: Request, collection_curie: str, concept_curie: str
):
    return await item_endpoint(request)


@router.get("/v/scheme/{scheme_curie}/{concept_curie}", summary="Get Concept")
@router.get("/v/vocab/{scheme_curie}/{concept_curie}", summary="Get Concept")
async def vocprez_scheme_concept(
    request: Request, scheme_curie: str, concept_curie: str
):
    return await item_endpoint(request)


@router.get("/v/object", summary="Get VocPrez Object")
async def item_endpoint(request: Request, vp_item: Optional[VocabItem] = None):
    """Returns a VocPrez skos:Concept, Collection, Vocabulary, or ConceptScheme in the requested profile & mediatype"""

    if not vp_item:
        vp_item = VocabItem(
            **request.path_params,
            **request.query_params,
            url_path=str(request.url.path)
        )
    prof_and_mt_info = ProfilesMediatypesInfo(request=request, classes=vp_item.classes)
    vp_item.selected_class = prof_and_mt_info.selected_class
    if prof_and_mt_info.profile == URIRef(
        "http://www.w3.org/ns/dx/conneg/altr-ext#alt-profile"
    ):
        return await return_profiles(
            classes=frozenset(vp_item.selected_class),
            prez_type="VocPrez",
            prof_and_mt_info=prof_and_mt_info,
        )
    item_query = generate_item_construct(vp_item, prof_and_mt_info.profile)
    (
        item_members_query,
        predicates_for_link_addition,
    ) = generate_listing_construct(vp_item, prof_and_mt_info.profile, 1, 5000)
    return await return_from_queries(
        [item_query, item_members_query],
        prof_and_mt_info.mediatype,
        prof_and_mt_info.profile,
        prof_and_mt_info.profile_headers,
        "VocPrez",
        predicates_for_link_addition,
    )
