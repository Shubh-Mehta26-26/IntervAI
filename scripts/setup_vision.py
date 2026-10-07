"""Explicit local model installation from publisher sources, never runtime downloads."""

import hashlib
import io
import tarfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
directory = ROOT / "vision/models"
directory.mkdir(parents=True, exist_ok=True)
with httpx.Client(timeout=180, follow_redirects=True) as client:
    weight = directory / "ssd.pb"
    if (
        not weight.exists()
        or hashlib.sha1(weight.read_bytes()).hexdigest()
        != "35d571ac314f1d32ae678a857f87cc0ef6b220e8"
    ):
        response = client.get(
            "https://storage.googleapis.com/download.tensorflow.org/models/object_detection/ssd_mobilenet_v2_coco_2018_03_29.tar.gz"
        )
        response.raise_for_status()
        archive = response.content
        assert (
            hashlib.sha1(archive).hexdigest()
            == "69c93d29e292bc9682396a5c78355b1dfe481b61"
        )  # upstream digest
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
            member = bundle.getmember(
                "ssd_mobilenet_v2_coco_2018_03_29/frozen_inference_graph.pb"
            )
            assert member.isfile() and member.size < 100_000_000
            data = bundle.extractfile(member).read()
        assert (
            hashlib.sha1(data).hexdigest() == "35d571ac314f1d32ae678a857f87cc0ef6b220e8"
        )
        (directory / "ssd.pb").write_bytes(data)
    for name, url in {
        "ssd.pbtxt": "https://raw.githubusercontent.com/opencv/opencv_extra/4.x/testdata/dnn/ssd_mobilenet_v2_coco_2018_03_29.pbtxt",
        "TENSORFLOW_LICENSE": "https://raw.githubusercontent.com/tensorflow/models/master/LICENSE",
        "OPENCV_LICENSE": "https://raw.githubusercontent.com/opencv/opencv/4.x/LICENSE",
    }.items():
        response = client.get(url)
        response.raise_for_status()
        if name == "ssd.pbtxt":
            assert (
                hashlib.sha256(response.content).hexdigest()
                == "cfbecf9447c384403ef5cf695f4cd0bb4840c1312938280350639a9a8e82d303"
            )
        (directory / name).write_bytes(response.content)
for path in directory.iterdir():
    print(path.name, hashlib.sha256(path.read_bytes()).hexdigest())
