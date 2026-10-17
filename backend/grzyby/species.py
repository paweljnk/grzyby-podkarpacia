"""Baza wiedzy o gatunkach: wczytanie i walidacja species/*.yaml."""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from .config import ROOT, load_yaml

SPECIES_DIR = ROOT / "species"
Grade = Literal["A", "B", "C"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Sourced(_Strict):
    zrodla: list[str]
    wiarygodnosc: Grade | None = None
    uwagi: str | None = None

    @field_validator("zrodla")
    @classmethod
    def _non_empty(cls, v):
        if not v:
            raise ValueError("każda reguła wymaga co najmniej jednego źródła")
        return v


class NazwaNaukowa(_Strict):
    aktualna: str
    synonimy: list[str]
    uwagi: str | None = None
    zrodla: list[str]


class TypTroficzny(Sourced):
    wartosc: Literal["mikoryzowy", "saprotroficzny"]


class Partner(Sourced):
    drzewo: str
    sila: Literal["silny", "umiarkowany", "slaby"]


class Wiek(Sourced):
    min_lat: int
    optimum_lat: tuple[int, int]


class Gleba(Sourced):
    odczyn: list[Literal["kwasny", "lekko_kwasny", "obojetny", "zasadowy"]]
    zyznosc: list[Literal["uboga", "srednia", "zyzna"]]
    uwilgotnienie: list[Literal["sucha", "swieza", "wilgotna", "bagienna"]]


class TSL(Sourced):
    preferowane: list[str]
    dopuszczalne: list[str]


class Wysokosc(Sourced):
    min_m: int
    max_m: int


class Sezon(Sourced):
    wysokosc_odniesienia_m: int
    start: str
    szczyt: tuple[str, str]
    koniec: str
    poprawka_wysokosci_dni_na_100m: float

    @model_validator(mode="after")
    def _order(self):
        days = [_doy(self.start), _doy(self.szczyt[0]), _doy(self.szczyt[1]), _doy(self.koniec)]
        if days != sorted(days):
            raise ValueError(f"sezon: daty nie są uporządkowane {self.start}..{self.koniec}")
        return self


class Opady(Sourced):
    okno_dni: int
    min_mm: float
    optimum_mm: tuple[float, float]


class Prog(_Strict):
    t_sr_od: float
    t_sr_do: float
    dni: tuple[int, int]


class Opoznienie(Sourced):
    progi: list[Prog]
    opad_istotny_mm: float

    @model_validator(mode="after")
    def _contiguous(self):
        for a, b in zip(self.progi, self.progi[1:]):
            if a.t_sr_do != b.t_sr_od:
                raise ValueError("progi opóźnienia muszą tworzyć ciągłe przedziały temperatur")
        for p in self.progi:
            if p.dni[0] > p.dni[1] or p.t_sr_od >= p.t_sr_do:
                raise ValueError("niepoprawny próg opóźnienia")
        return self


class Temperatura(Sourced):
    t_sr_min: float
    t_sr_optimum: tuple[float, float]
    t_sr_max: float

    @model_validator(mode="after")
    def _order(self):
        if not (self.t_sr_min <= self.t_sr_optimum[0] <= self.t_sr_optimum[1] <= self.t_sr_max):
            raise ValueError("temperatura: wymagane min <= optimum <= max")
        return self


class Susza(Sourced):
    dni_bez_opadu_kara_od: int
    bilans_14d_mm_kara_ponizej: float
    bilans_14d_mm_bramka_ponizej: float


class Przymrozek(Sourced):
    tmin_prog_c: float
    kara_pkt_za_dzien_7d: float


class Pogoda(_Strict):
    opady: Opady
    opoznienie_po_opadzie: Opoznienie
    temperatura: Temperatura
    susza: Susza
    przymrozek: Przymrozek


class Status(Sourced):
    wartosc: Literal["jadalny", "niejadalny", "trujacy", "smiertelnie_trujacy", "niepewny"]
    uwagi: list[str] = []


class Sprzecznosc(_Strict):
    temat: str
    opis: str
    zrodla: list[str]


class Weryfikacja(_Strict):
    status: Literal["wersja_robocza", "zatwierdzone"]
    zatwierdzil: str | None
    data: date | None


class Species(_Strict):
    id: str
    nazwa_polska: str
    nazwy_zwyczajowe: list[str]
    nazwa_naukowa: NazwaNaukowa
    typ_troficzny: TypTroficzny
    drzewa_partnerskie: list[Partner]
    wiek_drzewostanu: Wiek | None = None
    gleba: Gleba
    typy_siedliskowe: TSL
    wysokosc_npm: Wysokosc
    sezon: Sezon
    pogoda: Pogoda
    status: Status
    sobowtory: list[str]
    sprzecznosci: list[Sprzecznosc]
    weryfikacja: Weryfikacja

    def all_source_keys(self) -> set[str]:
        keys: set[str] = set(self.nazwa_naukowa.zrodla)

        def walk(o):
            if isinstance(o, BaseModel):
                if "zrodla" in type(o).model_fields:
                    keys.update(o.zrodla)
                for f in type(o).model_fields:
                    walk(getattr(o, f))
            elif isinstance(o, (list, tuple)):
                for x in o:
                    walk(x)
        walk(self)
        return keys


def _doy(mmdd: str) -> int:
    m, d = map(int, mmdd.split("-"))
    return date(2001, m, d).timetuple().tm_yday


def load_bibliography(directory: Path = SPECIES_DIR) -> dict[str, dict]:
    with open(directory / "_zrodla.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["zrodla"]


def load_species_file(path: Path) -> Species:
    with open(path, encoding="utf-8") as f:
        return Species.model_validate(yaml.safe_load(f))


@lru_cache
def all_species(directory: Path = SPECIES_DIR) -> dict[str, Species]:
    out = {}
    for p in sorted(directory.glob("*.yaml")):
        if p.name.startswith("_"):
            continue
        sp = load_species_file(p)
        if sp.id != p.stem:
            raise ValueError(f"{p.name}: id {sp.id!r} różni się od nazwy pliku")
        out[sp.id] = sp
    return out


def validate_cross_refs(species: dict[str, Species], bibliography: dict[str, dict]) -> list[str]:
    """Błędy odniesień: nieznane źródła, drzewa i typy siedliskowe spoza słowników."""
    vocab = load_yaml("slowniki.yaml")
    trees, tsl = set(vocab["drzewa"]), set(vocab["typy_siedliskowe"])
    errors = []
    for sp in species.values():
        for k in sp.all_source_keys() - set(bibliography):
            errors.append(f"{sp.id}: nieznane źródło {k!r}")
        for p in sp.drzewa_partnerskie:
            if p.drzewo not in trees:
                errors.append(f"{sp.id}: nieznane drzewo {p.drzewo!r}")
        for t in sp.typy_siedliskowe.preferowane + sp.typy_siedliskowe.dopuszczalne:
            if t not in tsl:
                errors.append(f"{sp.id}: nieznany typ siedliskowy {t!r}")
        if set(sp.typy_siedliskowe.preferowane) & set(sp.typy_siedliskowe.dopuszczalne):
            errors.append(f"{sp.id}: TSL jednocześnie preferowany i dopuszczalny")
        if sp.typ_troficzny.wartosc == "mikoryzowy" and not sp.drzewa_partnerskie:
            errors.append(f"{sp.id}: gatunek mikoryzowy bez drzew partnerskich")
    return errors
