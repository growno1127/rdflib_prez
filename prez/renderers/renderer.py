from abc import ABCMeta, abstractmethod
from typing import Dict, Optional, Union

from connegp import Connegp, Profile, RDF_MEDIATYPES, RDF_SERIALIZER_TYPES_MAP
from fastapi.responses import Response, JSONResponse, PlainTextResponse
from rdflib import Graph, URIRef, Literal, BNode
from rdflib.namespace import PROF, XSD

from config import *
from utils import templates


class Renderer(object, metaclass=ABCMeta):
    """Abstract class containing base logic for conditionally rendering based on profile & mediatype"""

    def __init__(
        self,
        request: object,
        profiles: Dict[str, Profile],
        default_profile_token: str,
        instance_uri: str,
    ) -> None:
        self.error = None
        # if default_profile_token == "alt":
        #     self.error = "You cannot specify 'alt' as the default profile."

        if default_profile_token not in profiles.keys():
            self.error = (
                f"The profile token you specified ({default_profile_token}) for the default profile "
                "is not in the list of profiles you supplied ({profiles})"
            )

        self.profiles = dict(profiles)
        # self.profiles["alt"] = alt
        self.request = request
        self.default_profile_token = default_profile_token
        self.instance_uri = instance_uri

        connegp = Connegp(request, self.profiles, default_profile_token)
        self.profile = connegp.profile
        self.mediatype = connegp.mediatype

        # make headers
        if self.error is None:
            self.headers = {
                "Link": f'<{self.profiles[self.profile].uri}>; rel="profile"',
                "Content-Type": self.mediatype,
                "Access-Control-Allow-Origin": "*",
            }
            self.headers["Link"] += ", " + self._make_header_link_tokens()
            self.headers["Link"] += ", " + self._make_header_link_list_profiles()

    def _make_header_link_tokens(self) -> str:
        """Creates the Link header tokens for the supported profiles"""
        individual_links = []
        link_header_template = '<http://www.w3.org/ns/dx/prof/Profile>; rel="type"; token="{}"; anchor=<{}>, '

        for token, profile in self.profiles.items():
            individual_links.append(link_header_template.format(token, profile.uri))

        return "".join(individual_links).rstrip(", ")

    def _make_header_link_list_profiles(self) -> str:
        """Creates the Link header URIs for each possible profile representation"""
        individual_links = []
        for token, profile in self.profiles.items():
            # create an individual Link statement per Media Type
            for mediatype in profile.mediatypes:
                # set the rel="self" just for this profile & mediatype
                if mediatype != "_internal":
                    if (
                        token == self.default_profile_token
                        and mediatype == self.profiles[self.profile].default_mediatype
                    ):
                        rel = "self"
                    else:
                        rel = "alternate"

                    individual_links.append(
                        '<{}?_profile={}&_mediatype={}>; rel="{}"; type="{}"; profile="{}", '.format(
                            self.instance_uri,
                            token,
                            mediatype,
                            rel,
                            mediatype,
                            profile.uri,
                        )
                    )

        # append to, or create, Link header
        return "".join(individual_links).rstrip(", ")

    def _generate_alt_rdf(self) -> Graph:
        """Creates a graph of the alternate profiles"""
        # Alt R Data Model as per https://www.w3.org/TR/dx-prof-conneg/#altr
        g = Graph()
        ALTR = Namespace("http://www.w3.org/ns/dx/conneg/altr#")
        g.bind("altr", ALTR)
        g.bind("dct", DCTERMS)
        g.bind("prof", PROF)

        instance_uri = URIRef(self.instance_uri)

        # for each Profile, lis it via its URI and give annotations
        for token, p in self.profiles.items():
            profile_uri = URIRef(p.uri)
            g.add((profile_uri, RDF.type, PROF.Profile))
            g.add((profile_uri, RDFS.label, Literal(p.label, datatype=XSD.string)))
            g.add((profile_uri, RDFS.comment, Literal(p.comment, datatype=XSD.string)))

        # for each Profile and Media Type, create a Representation
        for token, p in self.profiles.items():
            for mt in p.mediatypes:
                rep = BNode()
                g.add((rep, RDF.type, ALTR.Representation))
                g.add((rep, DCTERMS.conformsTo, URIRef(p.uri)))
                g.add((rep, URIRef(DCTERMS + "format"), Literal(mt)))
                g.add((rep, PROF.hasToken, Literal(token, datatype=XSD.token)))

                # if this is the default format for the Profile, say so
                if mt == p.default_mediatype:
                    g.add(
                        (
                            rep,
                            ALTR.isProfilesDefault,
                            Literal(True, datatype=XSD.boolean),
                        )
                    )

                # link this representation to the instances
                g.add((instance_uri, ALTR.hasRepresentation, rep))

                # if this is the default Profile and the default Media Type, set it as the instance's default Rep
                if token == self.default_profile_token and mt == p.default_mediatype:
                    g.add((instance_uri, ALTR.hasDefaultRepresentation, rep))

        return g

    def _make_rdf_response(self, item_uri, graph: Graph) -> Response:
        """Creates an RDF response from a Graph"""
        serial_mediatype = RDF_SERIALIZER_TYPES_MAP[self.mediatype]

        # remove labels from the graph
        query = f"""
        PREFIX geo: <{GEO}>
        CONSTRUCT {{ <{str(item_uri)}> ?p ?o ;
                      skos:inScheme ?cs .
                      ?o ?p2 ?o2 .
                      ?coll a geo:FeatureCollection ;
                        rdfs:member <{str(item_uri)}> .
                      ?dataset a dcat:Dataset ;
                        rdfs:member ?coll .

                        }}
              WHERE {{
                      <{str(item_uri)}> ?p ?o .
                      OPTIONAL {{
                      ?coll a geo:FeatureCollection ;
                        rdfs:member <{str(item_uri)}> .
                      ?dataset a dcat:Dataset ;
                        rdfs:member ?coll .
                        }}
                      OPTIONAL {{
                      <{str(item_uri)}> skos:inScheme ?cs .
                       }}
                OPTIONAL {{
                ?o ?p2 ?o2 .
                FILTER(ISBLANK(?o))
                       }}
                }}
        """
        filtered_g = Graph(namespace_manager=graph.namespace_manager)
        filtered_g += graph.query(query).graph

        response_text = filtered_g.serialize(format=serial_mediatype, encoding="utf-8")

        # destroy the triples in the triplestore, then delete the triplestore
        # this helps to prevent a memory leak in rdflib
        graph.store.remove((None, None, None))
        graph.destroy({})
        del graph

        return Response(response_text, media_type=self.mediatype)

    def _render_alt_html(
        self, template_context: Union[Dict, None]
    ) -> templates.TemplateResponse:
        """Renders the HTML representation of the alternate profiles using the 'alt.html' template"""
        _template_context = {
            "request": self.request,
            "uri": str(self.request.url),
            "profiles": self.profiles,
            "default_profile": self.profiles.get(self.default_profile_token),
        }
        if template_context is not None:
            _template_context.update(template_context)
        return templates.TemplateResponse(
            "alt.html", context=_template_context, headers=self.headers
        )

    def _render_alt_json(self) -> JSONResponse:
        """Renders the JSON representation of the alternate profiles"""
        return JSONResponse(
            content={
                "uri": str(self.request.url),
                "profiles": list(self.profiles.keys()),
                "default_profile": self.default_profile_token,
            },
            media_type="application/json",
            headers=self.headers,
        )

    def _render_alt(
        self, template_context: Union[Dict, None], alt_profiles_graph: Graph
    ) -> Union[templates.TemplateResponse, Response, JSONResponse]:
        """Renders the alternate profiles based on mediatype"""
        if self.mediatype == "text/html":
            return self._render_alt_html(template_context)
        elif self.mediatype in RDF_MEDIATYPES:
            response_text = alt_profiles_graph.serialize(format=self.mediatype)
            return Response(response_text, media_type=self.mediatype)
        else:  # application/json
            return self._render_alt_json()

    @abstractmethod
    def render(
        self, template_context: Optional[Dict] = None
    ) -> Union[
        PlainTextResponse, templates.TemplateResponse, Response, JSONResponse, None
    ]:
        """Renders this object based on a requested profile & mediatype"""
        if self.error is not None:
            return PlainTextResponse(self.error, status_code=400)
        elif self.profile == "alt":
            return self._render_alt(template_context)
        # extra profiles go here
        else:
            return None
