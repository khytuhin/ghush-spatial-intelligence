"""Stage and validate both artifacts before replacement; roll back ordinary write failures."""
import copy
import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

NAMES = ("adm3_metrics.geojson", "summary.json")

def canonical(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")

def content_id(geo, summary):
    geo, summary = copy.deepcopy(geo), copy.deepcopy(summary)
    geo.pop("data_id", None)
    summary["meta"].pop("data_id", None)
    summary["meta"].pop("generated_at", None)
    return hashlib.sha256(canonical([geo, summary])).hexdigest()

def bundle_id(bundle):
    data=copy.deepcopy(bundle)
    for product in data.values():
        if not isinstance(product,dict): continue
        product.pop('data_id',None)
        if 'meta' in product:
            product['meta'].pop('data_id',None)
            product['meta'].pop('generated_at',None)
    return hashlib.sha256(canonical(data)).hexdigest()

def publish_bundle(bundle,directory,*,as_of=None):
    from pipeline.bundle_contracts import validate_bundle
    from pipeline.contracts import validate_directory
    from pipeline.products import NAMES,JSON_NAMES
    directory=Path(directory)
    version=bundle_id(bundle)
    for name in JSON_NAMES:
        product=bundle[name]
        (product['meta'] if name=='summary.json' else product)['data_id']=version
    bundle['summary.json']['meta']['generated_at']=(as_of or datetime.now(timezone.utc)).isoformat()
    validate_bundle(bundle)
    try:
        old,_=validate_directory(directory)
        if old.get('data_id')==version:
            logging.info('publication=unchanged content_id=%s',version)
            return False
    except (OSError,ValueError,KeyError,TypeError): pass
    directory.mkdir(parents=True,exist_ok=True)
    originals={name:(directory/name).read_bytes() if (directory/name).exists() else None for name in NAMES}
    with tempfile.TemporaryDirectory(prefix='.staging-',dir=directory.parent) as tmp:
        stage=Path(tmp)
        for name in NAMES:
            (stage/name).write_bytes(bundle[name].encode('utf-8') if isinstance(bundle[name],str) else canonical(bundle[name]))
        validate_directory(stage)
        replaced=[]
        try:
            for name in NAMES:
                os.replace(stage/name,directory/name);replaced.append(name)
        except OSError:
            for name in replaced:
                if originals[name] is None: (directory/name).unlink(missing_ok=True)
                else: (directory/name).write_bytes(originals[name])
            raise
    logging.info('publication=changed content_id=%s artifacts=%d',version,len(NAMES))
    return True

def publish(geo, summary, directory, *, as_of=None):
    from pipeline.contracts import validate, validate_directory
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    version = content_id(geo, summary)
    geo["data_id"] = summary["meta"]["data_id"] = version
    summary["meta"]["generated_at"] = (as_of or datetime.now(timezone.utc)).isoformat()
    validate(geo, summary)
    try:
        old_geo, old_summary = validate_directory(directory)
        if old_geo["data_id"] == version:
            logging.info("publication=unchanged content_id=%s", version)
            return False
    except (OSError, ValueError, KeyError, TypeError):
        pass
    originals = {name: (directory / name).read_bytes() if (directory / name).exists() else None for name in NAMES}
    with tempfile.TemporaryDirectory(prefix=".staging-", dir=directory.parent) as tmp:
        stage = Path(tmp)
        for name, product in zip(NAMES, (geo, summary)):
            (stage / name).write_bytes(canonical(product))
        validate_directory(stage)
        replaced = []
        try:
            for name in NAMES:
                os.replace(stage / name, directory / name)
                replaced.append(name)
        except OSError:
            for name in replaced:
                if originals[name] is None:
                    (directory / name).unlink(missing_ok=True)
                else:
                    (directory / name).write_bytes(originals[name])
            raise
    logging.info("publication=changed content_id=%s", version)
    return True
