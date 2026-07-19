#!/usr/bin/env -S uv run --no-project --with duckdb python
"""
Transform the EU CosIng (Cosmetic Ingredient Database) into principled RDF for
the kg.toxindex.com knowledge graph.

Source bricks (see .bb/dependencies.txt):
  - eu-cosing-ingredients : brick/cosing_ingredients.parquet  (24k ingredients:
        INCI name, CAS, EC, declared function(s), restriction/annex reference)
  - cosing                : brick/annex-{ii..vi}.parquet       (regulatory annexes:
        max concentration, conditions of use)
  - pubchem-identifiers-structures : cas_numbers.parquet + compounds.parquet
        (the identifier-mapping stage: CAS -> CID -> InChIKey)

Model  (one node per CosIng ingredient record):
  <cosing-kg/ingredient/{ref}>
     a  bbendp:cosmetic-ingredient-use ;          # subClassOf obo:IAO_0000027 (data item)
     obo:IAO_0000136  <compound/{InChIKey}> ;      # is about (compound-bridge hub)
     rdfs:label       "<INCI name>" ;
     bb:hasFunction   "<function>" ;               # one per declared function
     bb:regulatoryAnnex "III" ;                    # parsed annex (roman)
     bb:regulatoryStatus "restricted" ;            # prohibited/restricted/colorant/preservative/uv-filter
     bb:restrictionRef  "III/249" ;                # raw annex reference (one per line)
     bb:maxConcentration "5%" ;                    # from matched annex row (best-effort)
     bb:conditionsOfUse  "..." ;                   # from matched annex row (best-effort)
     bb:casNumber "..." ; bb:ecNumber "..." ; bb:cosingRefNo "..." ;
     dcterms:source "EU CosIng (Cosmetic Ingredient Database)" ;
     prov:wasDerivedFrom <this repo> .

Compound identity: CAS -> InChIKey via PubChem identifier map. Unmapped rows get a
deterministic https://biobricks.ai/compound/unmapped/<slug> node carrying skos:notation
so they can be bridged later.

Output: brick/cosing-kg.nt  (named graph https://biobricks.ai/graph/cosing-kg)
"""
import json, re, pathlib
import duckdb

HERE  = pathlib.Path(__file__).resolve().parent
TERMS = json.load(open(HERE / "terms.json"))
OUT   = pathlib.Path("brick"); OUT.mkdir(parents=True, exist_ok=True)
NT    = OUT / "cosing-kg.nt"
GRAPH = "https://biobricks.ai/graph/cosing-kg"
REPO  = "https://github.com/biobricks-ai/cosing-kg"

# upstream brick parquet locations (biobricks BBLIB / raid mirror)
BB = pathlib.Path("/mnt/raid2/biobricks")
ING  = BB / "eu-cosing-ingredients/brick/cosing_ingredients.parquet"
CAS  = BB / "pubchem-identifiers-structures/brick/cas_numbers.parquet"
CMP  = BB / "pubchem-identifiers-structures/brick/compounds.parquet"
ANNEX_FILES = {"II":"annex-ii","III":"annex-iii","IV":"annex-iv","V":"annex-v","VI":"annex-vi"}

# IRIs / prefixes
BASE   = "https://biobricks.ai/cosing-kg/ingredient/"
CPD    = "https://biobricks.ai/compound/"
UNMAP  = "https://biobricks.ai/compound/unmapped/"
ENDP   = TERMS["endpoint"]["iri"]
BB_NS  = "https://biobricks.ai/ontology/"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS_LBL = "http://www.w3.org/2000/01/rdf-schema#label"
RDFS_SUB = "http://www.w3.org/2000/01/rdf-schema#subClassOf"
RDFS_CMT = "http://www.w3.org/2000/01/rdf-schema#comment"
IAO_ABOUT= "http://purl.obolibrary.org/obo/IAO_0000136"
SKOS_NOT = "http://www.w3.org/2004/02/skos/core#notation"
DCT_SRC  = "http://purl.org/dc/terms/source"
PROV_DER = "http://www.w3.org/ns/prov#wasDerivedFrom"
XSD_STR  = "http://www.w3.org/2001/XMLSchema#string"
SOURCE   = "EU CosIng (Cosmetic Ingredient Database)"

# annex reference like "III/249", "II/358 R1", possibly one per line
ANNEX_RE = re.compile(r'\b(I{1,3}|IV|V|VI)\s*/\s*([0-9A-Za-z]+)')

def esc(s):
    return (s.replace('\\','\\\\').replace('"','\\"')
             .replace('\n',' ').replace('\r',' ').replace('\t',' ').strip())

def slug(s):
    return re.sub(r'[^0-9A-Za-z._-]+','-', s.strip()).strip('-')

def blank(v):
    return v is None or str(v).strip() in ('', '-')


def load_annex(con):
    """(annex_roman, normalized_ref) -> (max_conc, conditions)"""
    idx = {}
    for roman, f in ANNEX_FILES.items():
        p = BB / "cosing/brick" / (f + ".parquet")
        if not p.exists():
            continue
        cols = [r[0] for r in con.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{p}')").fetchall()]
        mc = "Maximum concentration in ready for use preparation"
        co = "Wording of conditions of use and warnings"
        mc_e = f'"{mc}"' if mc in cols else 'NULL'
        co_e = f'"{co}"' if co in cols else 'NULL'
        rows = con.execute(
            f'SELECT CAST("Reference Number" AS VARCHAR), {mc_e}, {co_e} '
            f"FROM read_parquet('{p}')").fetchall()
        for ref, maxc, cond in rows:
            if ref is None:
                continue
            key = (roman, re.sub(r'\s+','', str(ref)).lower())
            idx[key] = (maxc, cond)
    return idx


def main():
    con = duckdb.connect()
    con.execute("PRAGMA threads=4")

    # CAS -> InChIKey map (identifier-mapping stage)
    con.execute(f"""
        CREATE TEMP TABLE casik AS
        SELECT m.cas AS cas, MIN(c.inchikey) AS inchikey
        FROM (SELECT trim(cas) cas, cid FROM read_parquet('{CAS}')) m
        JOIN (SELECT cid, inchikey FROM read_parquet('{CMP}') WHERE inchikey IS NOT NULL) c
          ON m.cid = c.cid
        GROUP BY m.cas
    """)
    annex = load_annex(con)

    rows = con.execute(f"""
        SELECT cosing_ref_no, inci_name, cas_number, ec_number,
               chemical_name, restriction, function
        FROM read_parquet('{ING}')
    """).fetchall()

    n_row=n_trip=0; n_mapped=0; n_unmapped=0; n_restricted=0
    compounds=set(); functions=set(); annex_hits=0
    stat_counts={}

    with open(NT,'w') as out:
        def w(s,p,o_iri=None,lit=None,dt=None):
            nonlocal n_trip
            if o_iri is not None:
                out.write(f"<{s}> <{p}> <{o_iri}> .\n")
            else:
                out.write(f'<{s}> <{p}> "{esc(lit)}"'+(f"^^<{dt}>" if dt else "")+" .\n")
            n_trip+=1

        # endpoint class declaration
        w(ENDP, RDF_TYPE, o_iri="http://www.w3.org/2002/07/owl#Class")
        w(ENDP, RDFS_SUB, o_iri=TERMS["endpoint"]["subClassOf"])
        w(ENDP, RDFS_LBL, lit=TERMS["endpoint"]["label"])
        w(ENDP, RDFS_CMT, lit=TERMS["endpoint"]["comment"])

        for ref, inci, cas, ec, chem, restr, func in rows:
            ref=(ref or '').strip()
            if not ref:
                continue
            n_row+=1
            node=f"{BASE}{slug(ref)}"
            cas_c=None if blank(cas) else cas.strip()
            ec_c =None if blank(ec)  else ec.strip()

            # compound identity
            ik=None
            if cas_c:
                r=con.execute("SELECT inchikey FROM casik WHERE cas=?",[cas_c]).fetchone()
                ik=r[0] if r else None
            if ik:
                cpd=f"{CPD}{ik}"; n_mapped+=1
            else:
                if cas_c:   cpd=f"{UNMAP}CAS{slug(cas_c)}"
                elif ec_c:  cpd=f"{UNMAP}EC{slug(ec_c)}"
                else:       cpd=f"{UNMAP}cosing{slug(ref)}"
                n_unmapped+=1
            compounds.add(cpd)

            w(node, RDF_TYPE, o_iri=ENDP)
            w(node, IAO_ABOUT, o_iri=cpd)
            if not blank(inci): w(node, RDFS_LBL, lit=inci.strip())
            w(node, f"{BB_NS}cosingRefNo", lit=ref)
            if cas_c:
                w(node, f"{BB_NS}casNumber", lit=cas_c)
                w(cpd, SKOS_NOT, lit=f"CAS:{cas_c}")
            if ec_c:
                w(node, f"{BB_NS}ecNumber", lit=ec_c)
                w(cpd, SKOS_NOT, lit=f"EC:{ec_c}")
            if not blank(chem): w(node, f"{BB_NS}chemicalName", lit=chem.strip())

            # functions (comma separated)
            if not blank(func):
                for fn in func.split(','):
                    fn=fn.strip()
                    if fn:
                        w(node, f"{BB_NS}hasFunction", lit=fn)
                        functions.add(fn.upper())

            # restriction / annex
            if not blank(restr):
                n_restricted+=1
                seen=set()
                for m in ANNEX_RE.finditer(restr):
                    roman=m.group(1).upper(); anum=m.group(2)
                    raw=f"{roman}/{anum}"
                    if raw in seen: continue
                    seen.add(raw)
                    w(node, f"{BB_NS}restrictionRef", lit=raw)
                    w(node, f"{BB_NS}regulatoryAnnex", lit=roman)
                    meta=TERMS["annexes"].get(roman)
                    if meta:
                        w(node, f"{BB_NS}regulatoryStatus", lit=meta["status"])
                        stat_counts[meta["status"]]=stat_counts.get(meta["status"],0)+1
                    a=annex.get((roman, re.sub(r'\s+','',anum).lower()))
                    if a:
                        maxc, cond = a
                        if not blank(maxc): w(node, f"{BB_NS}maxConcentration", lit=maxc);
                        if not blank(cond): w(node, f"{BB_NS}conditionsOfUse", lit=cond)
                        annex_hits+=1
                # preserve raw restriction text too
                w(node, f"{BB_NS}restrictionText", lit=restr)

            w(node, DCT_SRC, lit=SOURCE)
            w(node, PROV_DER, o_iri=REPO)

    print(json.dumps({
        "rows": n_row, "triples": n_trip,
        "distinct_compounds": len(compounds),
        "mapped_to_inchikey": n_mapped,
        "unmapped_fallback": n_unmapped,
        "distinct_functions": len(functions),
        "restricted_ingredients": n_restricted,
        "annex_concentration_hits": annex_hits,
        "status_counts": stat_counts,
        "output": str(NT), "graph": GRAPH,
    }, indent=2))

if __name__=="__main__":
    main()
