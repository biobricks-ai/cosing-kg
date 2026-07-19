# cosing-kg

Transforms the **EU CosIng** (Cosmetic Ingredient Database) tabular bricks into
**principled RDF** for the biobricks knowledge graph serving kg.toxindex.com.

CosIng is the European Commission database of cosmetic substances and ingredients
regulated under Cosmetics [Regulation (EC) No 1223/2009](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:02009R1223-20190813).
It carries each ingredient's INCI name, CAS/EC numbers, declared cosmetic
**function(s)** (e.g. preservative, UV filter, surfactant, skin conditioning) and
any **restriction / prohibition** under the regulatory Annexes
(II prohibited, III restricted, IV colorants, V preservatives, VI UV filters).

## What it produces

One node per CosIng ingredient record, typed as the minted endpoint class
`https://biobricks.ai/endpoint/cosmetic-ingredient-use`
(subClassOf `obo:IAO_0000027`, *data item*):

```
<https://biobricks.ai/cosing-kg/ingredient/{cosing_ref_no}>
    a  bbendp:cosmetic-ingredient-use ;
    obo:IAO_0000136   <https://biobricks.ai/compound/{InChIKey}> ;  # is about (compound-bridge hub)
    rdfs:label        "<INCI name>" ;
    bb:hasFunction    "<declared function>" ;      # one per function
    bb:regulatoryAnnex  "III" ;                    # parsed annex (roman numeral)
    bb:regulatoryStatus "restricted" ;             # prohibited/restricted/colorant/preservative/uv-filter
    bb:restrictionRef   "III/249" ;                # raw annex reference
    bb:maxConcentration "5%" ;                     # from the matched Annex row (best-effort)
    bb:conditionsOfUse  "..." ;                    # from the matched Annex row (best-effort)
    bb:casNumber "..." ; bb:ecNumber "..." ; bb:chemicalName "..." ; bb:cosingRefNo "..." ;
    dcterms:source      "EU CosIng (Cosmetic Ingredient Database)" ;
    prov:wasDerivedFrom <https://github.com/biobricks-ai/cosing-kg> .
```

Prefixes: `obo:` `http://purl.obolibrary.org/obo/`, `bb:` `https://biobricks.ai/ontology/`,
`bbendp:` `https://biobricks.ai/endpoint/`, `dcterms:` `http://purl.org/dc/terms/`,
`prov:` `http://www.w3.org/ns/prov#`, `skos:` `http://www.w3.org/2004/02/skos/core#`.

Output: `brick/cosing-kg.nt`, loaded as the named graph
`https://biobricks.ai/graph/cosing-kg`.

## Compound identity

Every record joins the KG through the
[compound-bridge](https://github.com/biobricks-ai/compound-bridge) InChIKey hub
`https://biobricks.ai/compound/<InChIKey>`. CosIng rows carry only CAS/EC numbers,
so identity is resolved via the **identifier-mapping stage**
([pubchem-identifiers-structures](https://github.com/biobricks-ai/pubchem-identifiers-structures):
CAS → CID → InChIKey). Rows that do not resolve (botanical extracts, polymers,
mixtures, unlisted CAS) fall back to a deterministic
`https://biobricks.ai/compound/unmapped/<slug>` node carrying `skos:notation`
(`CAS:…` / `EC:…`) so they can be bridged later.

Mapping rate: **5,956 / 24,094** ingredient rows resolve to a canonical InChIKey
(about 24.7% of all rows, about 45.9% of the 12,989 rows that carry a CAS number).

## Sources / dependencies

Pinned in `.bb/dependencies.txt`:
- [eu-cosing-ingredients](https://github.com/biobricks-ai/eu-cosing-ingredients) — the full 24,094-ingredient table (INCI, CAS, EC, function, restriction).
- [cosing](https://github.com/biobricks-ai/cosing) — the Annex II–VI tables (max concentration, conditions of use), joined to enrich restricted substances.
- [pubchem-identifiers-structures](https://github.com/biobricks-ai/pubchem-identifiers-structures) — the CAS → InChIKey identifier map.

## Build

`dvc repro` (needs the dependencies pinned in `.bb/dependencies.txt` installed via
`biobricks install`). Emits `brick/cosing-kg.nt`; the KG orchestrator loads it
centrally into Virtuoso.
