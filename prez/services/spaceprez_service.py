from typing import Optional

from rdflib import Namespace
from rdflib.namespace import RDFS, DCAT, DCTERMS

from config import *
from services.sparql_utils import *


async def list_datasets():
    q = f"""
        PREFIX dcat: <{DCAT}>
        PREFIX dcterms: <{DCTERMS}>
        PREFIX rdfs: <{RDFS}>
        PREFIX skos: <{SKOS}>
        SELECT DISTINCT ?d ?id ?label
        WHERE {{
            ?d a dcat:Dataset ;
                dcterms:identifier ?id ;
                skos:prefLabel|dcterms:title|rdfs:label ?label .
        }}
    """
    r = await sparql_query(q)
    if r[0]:
        return r[1]
    else:
        raise Exception(f"SPARQL query error code {r[1]}: {r[2]}")


async def get_dataset_construct(
    dataset_id: Optional[str] = None, dataset_uri: Optional[str] = None
):
    if dataset_id is None and dataset_uri is None:
        raise ValueError("Either an ID or a URI must be provided for a SPARQL query")

    # when querying by ID via regular URL path
    query_by_id = f"""
        ?d dcterms:identifier ?id ;
            a dcat:Dataset .
        FILTER (STR(?id) = "{dataset_id}")
    """
    # when querying by URI via /object?uri=...
    query_by_uri = f"""
        BIND (<{dataset_uri}> as ?d)
        ?d a dcat:Dataset .
    """

    q = f"""
        PREFIX dcat: <{DCAT}>
        PREFIX dcterms: <{DCTERMS}>
        PREFIX rdfs: <{RDFS}>
        CONSTRUCT {{
            ?d ?p1 ?o1 .
            ?p1 rdfs:label ?p1Label .
            ?o1 rdfs:label ?o1Label .
        }}
        WHERE {{
            {query_by_id if dataset_id is not None else query_by_uri}
            ?d ?p1 ?o1 .
            OPTIONAL {{
                ?p1 rdfs:label ?p1Label .
                FILTER(lang(?p1Label) = "" || lang(?p1Label) = "en")
            }}
            OPTIONAL {{
                ?o1 rdfs:label ?o1Label .
                FILTER(lang(?o1Label) = "" || lang(?o1Label) = "en")
            }}
        }}
    """
    r = await sparql_construct(q)
    if r[0]:
        return r[1]
    else:
        raise Exception(f"SPARQL query error code {r[1]}: {r[2]}")


async def list_collections(dataset_id: str):
    q = f"""
        PREFIX dcat: <{DCAT}>
        PREFIX dcterms: <{DCTERMS}>
        PREFIX geo: <{GEO}>
        PREFIX rdfs: <{RDFS}>
        PREFIX skos: <{SKOS}>
        SELECT DISTINCT *
        WHERE {{
            ?d dcterms:identifier ?d_id ;
                a dcat:Dataset ;
                skos:prefLabel|dcterms:title|rdfs:label ?d_label .
            FILTER (STR(?d_id) = "{dataset_id}")
            ?coll a geo:FeatureCollection ;
                dcterms:isPartOf ?d ;
                dcterms:identifier ?id ;
                skos:prefLabel|dcterms:title|rdfs:label ?label .
        }}
    """
    r = await sparql_query(q)
    if r[0]:
        return r[1]
    else:
        raise Exception(f"SPARQL query error code {r[1]}: {r[2]}")


async def get_collection_construct(
    dataset_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    collection_uri: Optional[str] = None,
):
    if collection_id is None and collection_uri is None:
        raise ValueError("Either an ID or a URI must be provided for a SPARQL query")

    # when querying by ID via regular URL path
    query_by_id = f"""
        FILTER (STR(?d_id) = "{dataset_id}")
        ?coll a geo:FeatureCollection ;
            dcterms:isPartOf ?d ;
            dcterms:identifier ?id .
        FILTER (STR(?id) = "{collection_id}")
    """
    # when querying by URI via /object?uri=...
    query_by_uri = f"""
        BIND (<{collection_uri}> as ?coll)
        ?coll a geo:FeatureCollection .
    """

    q = f"""
        PREFIX dcat: <{DCAT}>
        PREFIX dcterms: <{DCTERMS}>
        PREFIX geo: <{GEO}>
        PREFIX rdfs: <{RDFS}>
        PREFIX skos: <{SKOS}>
        CONSTRUCT {{
            ?coll ?p1 ?o1 .
            ?p1 rdfs:label ?p1Label .
            ?o1 rdfs:label ?o1Label .

            ?d a dcat:Dataset ;
                dcterms:identifier ?d_id ;
                ?label_pred ?d_label .
        }}
        WHERE {{
            {query_by_id if collection_id is not None else query_by_uri}
            ?coll ?p1 ?o1 ;
                dcterms:isPartOf ?d .
            ?d a dcat:Dataset ;
                dcterms:identifier ?d_id ;
                ?label_pred ?d_label .
            FILTER (?label_pred IN (skos:prefLabel, dcterms:title, rdfs:label))
            OPTIONAL {{
                ?p1 rdfs:label ?p1Label .
                FILTER(lang(?p1Label) = "" || lang(?p1Label) = "en")
            }}
            OPTIONAL {{
                ?o1 rdfs:label ?o1Label .
                FILTER(lang(?o1Label) = "" || lang(?o1Label) = "en")
            }}
        }}
    """
    r = await sparql_construct(q)
    if r[0]:
        return r[1]
    else:
        raise Exception(f"SPARQL query error code {r[1]}: {r[2]}")


async def list_features(dataset_id: str, collection_id: str):
    q = f"""
        PREFIX dcat: <{DCAT}>
        PREFIX dcterms: <{DCTERMS}>
        PREFIX geo: <{GEO}>
        PREFIX rdfs: <{RDFS}>
        PREFIX skos: <{SKOS}>
        SELECT DISTINCT *
        WHERE {{
            ?d dcterms:identifier ?d_id ;
                a dcat:Dataset ;
                skos:prefLabel|dcterms:title|rdfs:label ?d_label .
            FILTER (STR(?d_id) = "{dataset_id}")
            ?coll a geo:FeatureCollection ;
                dcterms:isPartOf ?d ;
                dcterms:identifier ?coll_id ;
                skos:prefLabel|dcterms:title|rdfs:label ?coll_label .
            FILTER (STR(?coll_id) = "{collection_id}")
            ?f a geo:Feature ;
                dcterms:isPartOf ?coll ;
                dcterms:identifier ?id .
                
            OPTIONAL {{
                ?f skos:prefLabel|dcterms:title|rdfs:label ?label .
            }}
        }}
    """
    r = await sparql_query(q)
    if r[0]:
        return r[1]
    else:
        raise Exception(f"SPARQL query error code {r[1]}: {r[2]}")

async def get_feature_construct(
    dataset_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    feature_id: Optional[str] = None,
    feature_uri: Optional[str] = None,
):
    if feature_id is None and feature_uri is None:
        raise ValueError("Either an ID or a URI must be provided for a SPARQL query")

    # when querying by ID via regular URL path
    query_by_id = f"""
        FILTER (STR(?d_id) = "{dataset_id}")
        ?coll a geo:FeatureCollection ;
            dcterms:isPartOf ?d ;
            dcterms:identifier ?coll_id .
        FILTER (STR(?coll_id) = "{collection_id}")
        ?f a geo:Feature ;
            dcterms:isPartOf ?coll ;
            dcterms:identifier ?id .
        FILTER (STR(?id) = "{feature_id}")
    """
    # when querying by URI via /object?uri=...
    query_by_uri = f"""
        BIND (<{feature_uri}> as ?f)
        ?f a geo:Feature .
    """

    q = f"""
        PREFIX dcat: <{DCAT}>
        PREFIX dcterms: <{DCTERMS}>
        PREFIX geo: <{GEO}>
        PREFIX rdfs: <{RDFS}>
        PREFIX skos: <{SKOS}>
        CONSTRUCT {{
            ?f ?p1 ?o1 .
            ?p1 rdfs:label ?p1Label .
            ?o1 rdfs:label ?o1Label .

            ?coll a geo:FeatureCollection ;
                dcterms:identifier ?coll_id ;
                ?label_pred ?coll_label .
            
            ?d a dcat:Dataset ;
                dcterms:identifier ?d_id ;
                ?label_pred ?d_label .
        }}
        WHERE {{
            {query_by_id if feature_id is not None else query_by_uri}
            ?f ?p1 ?o1 ;
                dcterms:isPartOf ?coll .
            ?coll a geo:FeatureCollection ;
                dcterms:identifier ?coll_id ;
                ?label_pred ?coll_label .
            ?d a dcat:Dataset ;
                dcterms:identifier ?d_id ;
                ?label_pred ?d_label .
            FILTER (?label_pred IN (skos:prefLabel, dcterms:title, rdfs:label))
            OPTIONAL {{
                ?p1 rdfs:label ?p1Label .
                FILTER(lang(?p1Label) = "" || lang(?p1Label) = "en")
            }}
            OPTIONAL {{
                ?o1 rdfs:label ?o1Label .
                FILTER(lang(?o1Label) = "" || lang(?o1Label) = "en")
            }}
        }}
    """
    r = await sparql_construct(q)
    if r[0]:
        return r[1]
    else:
        raise Exception(f"SPARQL query error code {r[1]}: {r[2]}")
