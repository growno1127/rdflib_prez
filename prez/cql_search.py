from typing import Optional, Tuple
import re

from fastapi import HTTPException

from prez.config import CQL_PROPS


class CQLSearch(object):
    def __init__(
        self,
        filter: str,
        datasets: str,
        collections: str,
        filter_lang: Optional[str] = None,
        filter_crs: Optional[str] = None,
    ) -> None:
        self.filter = filter
        self.datasets = datasets
        self.collections = collections
        self.filter_lang = filter_lang
        self.filter_crs = filter_crs
        self.query = ""

    def _check_prop_exists(self, prop: str) -> bool:
        return prop in CQL_PROPS.keys()

    def _check_type(self, prop: str, val: str) -> bool:
        prop_type = CQL_PROPS[prop].get("type")
        if prop_type is not None:
            correct_type = False
            match prop_type:
                case "integer":
                    if re.match(r"(-|\+)?\d+", val):
                        correct_type = True
                case "float":
                    if re.match(r"(-|\+)?\d+\.\d+", val):
                        correct_type = True
                case "string":
                    if re.match(r'".+"', val):
                        correct_type = True
                case _:  # invalid prop type?
                    pass
            return correct_type
        else:
            return True

    def _parse_eq_ops(self, f: str) -> str:
        # validate
        exps = re.findall(
            r'(\w+)\s?(<>|<=|>=|=|<|>)\s?(".+"|\d+(?:\.\d+)?)', f, flags=re.IGNORECASE
        )
        for prop, op, val in exps:
            if not self._check_prop_exists(prop):
                raise HTTPException(
                    status_code=400,
                    detail=f"{prop} is not a valid property. Please consult /queryables for the list of available properties.",
                )
            if not self._check_type(prop, val):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid type for the property {prop}, which is of type {CQL_PROPS[prop].get('type')}",
                )

        # string replace
        return re.sub(
            r'(\w+)\s?(<>|<=|>=|=|<|>)\s?(".+"|\d+(?:\.\d+)?)',
            lambda x: f'?{x.group(1)} {"!=" if x.group(2) == "<>" else x.group(2)} {x.group(3)}',
            f,
            flags=re.IGNORECASE,
        )

    def _parse_between(self, f: str) -> str:
        # validate
        exps = re.findall(
            r'(\w+) between (".+"|\d+(?:\.\d+)?) and (".+"|\d+(?:\.\d+)?)',
            f,
            flags=re.IGNORECASE,
        )
        for prop, val1, val2 in exps:
            if not self._check_prop_exists(prop):
                raise HTTPException(
                    status_code=400,
                    detail=f"{prop} is not a valid property. Please consult /queryables for the list of available properties.",
                )
            if not self._check_type(prop, val1) or not self._check_type(prop, val2):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid type for the property {prop}, which is of type {CQL_PROPS[prop].get('type')}",
                )

        # string replace
        return re.sub(
            r'(\w+) between (".+"|\d+(?:\.\d+)?) and (".+"|\d+(?:\.\d+)?)',
            r"(?\1 >= \2 && ?\1 <= \3)",
            f,
            flags=re.IGNORECASE,
        )

    def _parse_or(self, f: str) -> str:
        return re.sub(r" or ", r" || ", f, flags=re.IGNORECASE)

    def _parse_and(self, f: str) -> str:
        return re.sub(r" and ", r" && ", f, flags=re.IGNORECASE)

    def _parse_like(self, f: str) -> str:
        # validate
        exps = re.findall(r'(\w+) like (".+")', f, flags=re.IGNORECASE)
        for prop, val in exps:
            if not self._check_prop_exists(prop):
                raise HTTPException(
                    status_code=400,
                    detail=f"{prop} is not a valid property. Please consult /queryables for the list of available properties.",
                )
            if not self._check_type(prop, val):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid type for the property {prop}, which is of type {CQL_PROPS[prop].get('type')}",
                )

        # string replace
        return re.sub(
            r'(\w+) like (".+")', r'regex(?\1, \2, "i" )', f, flags=re.IGNORECASE
        )

    def _parse_is(self, f: str) -> str:
        return re.sub(
            r"(\w+) is (not )?null",
            lambda x: f'{"NOT " if x.group(2) is None else ""}EXISTS {{?f {CQL_PROPS[x.group(1)]["qname"]} ?{x.group(1)}}}',
            f,
            flags=re.IGNORECASE,
        )

    def _parse_in(self, f: str) -> str:
        # validate
        exps = re.findall(
            r'(\w+) (in) (\((?:(?:".+"|\d+),\s?)*(?:".+"|\d+)\))',
            f,
            flags=re.IGNORECASE,
        )
        for prop, op, val in exps:
            if not self._check_prop_exists(prop):
                raise HTTPException(
                    status_code=400,
                    detail=f"{prop} is not a valid property. Please consult /queryables for the list of available properties.",
                )
            for element in val.strip("()").split(","):
                if not self._check_type(prop, element.strip()):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid type for the property {prop}, which is of type {CQL_PROPS[prop].get('type')}",
                    )

        # string replace
        return re.sub(
            r'(\w+) (in) (\((?:(?:".+"|\d+),\s?)*(?:".+"|\d+)\))',
            r"?\1 \2 \3",
            f,
            flags=re.IGNORECASE,
        )

    def generate_query(self) -> Tuple[str, str, str]:
        self.dataset_query = ""

        if self.datasets != "":
            self.dataset_query = f"""
                BIND(STR(?d_id) AS ?d_id_str)
                VALUES ?d_id_str {{{" ".join([f'"{d.strip()}"' for d in self.datasets.split(',')])}}}
            """

        self.collection_query = ""

        if self.collections != "":
            self.collection_query = f"""
                BIND(STR(?coll_id) AS ?coll_id_str)
                VALUES ?coll_id_str {{{" ".join([f'"{coll.strip()}"' for coll in self.collections.split(',')])}}}
            """

        self.query = ""

        if self.filter != "":
            self.filter = self._parse_eq_ops(self.filter)
            self.filter = self._parse_between(self.filter)
            self.filter = self._parse_or(self.filter)
            self.filter = self._parse_and(self.filter)
            self.filter = self._parse_like(self.filter)
            self.filter = self._parse_is(self.filter)
            self.filter = self._parse_in(self.filter)

            for prop in CQL_PROPS.keys():
                if f"?{prop}" in self.filter:
                    # checks for exists/is null to avoid inserting unnecessary triples
                    # if the only reference of a prop is with EXISTS, then don't insert triple
                    if len(re.findall(f"\?{prop}", self.filter)) > len(
                        re.findall(
                            f"EXISTS\s?{{\s?\?f {CQL_PROPS[prop]['qname']} \?{prop}",
                            self.filter,
                            flags=re.IGNORECASE,
                        )
                    ):
                        self.query += f"\n?f {CQL_PROPS[prop]['qname']} ?{prop} ."

            self.filter = f"FILTER({self.filter})"
            self.query += f"\n{self.filter}"
        return self.dataset_query, self.collection_query, self.query
