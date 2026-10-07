# Local computer vision assets

Runtime: `opencv-python-headless` 4.12.0.88 (OpenCV, Apache-2.0 with retained
third-party notices), NumPy 2.2.6 (BSD-3-Clause), Pillow 12.3.0 (HPND).
Installed package distributions retain their complete licenses.

Model: TensorFlow Object Detection Model Zoo SSD MobileNet V2 COCO,
`ssd_mobilenet_v2_coco_2018_03_29`. The TensorFlow Models research code is
Apache-2.0; the publisher's model artifact and research provenance are retained.
No AGPL YOLO distribution or paid/cloud inference provider is included.
The model only supplies COCO category boxes/scores; this app consumes person and
cell-phone categories and discards boxes/images. No facial identity model exists.

Sources:

- [TensorFlow model zoo](https://github.com/tensorflow/models/blob/master/research/object_detection/g3doc/tf1_detection_zoo.md)
- [TensorFlow research license](https://github.com/tensorflow/models/blob/master/LICENSE)
- [OpenCV published archive/graph digests](https://github.com/opencv/opencv_extra/blob/4.x/testdata/dnn/download_models.py)
- [OpenCV generated graph description](https://github.com/opencv/opencv_extra/blob/4.x/testdata/dnn/ssd_mobilenet_v2_coco_2018_03_29.pbtxt)
- [OpenCV license](https://github.com/opencv/opencv/blob/4.x/LICENSE)

`ssd.pbtxt` is the generated TensorFlow graph description published as OpenCV
test data, rather than an independently trained model. OpenCV Extra has no
separate top-level license file; retain its exact provenance and the upstream
TensorFlow/OpenCV notices rather than claiming every unrelated test asset in
that repository has one blanket license. The implementation uses only this graph
description and the explicitly publisher-checksummed TensorFlow weights.
Academic/local distribution retains these notices. Production redistribution
must retain publisher and dependency licenses, and review dataset/image rights
separately from library licensing. COCO training images are not redistributed.

`scripts/setup_vision.py` downloads fixed publisher URLs, checks the published
archive/member SHA-1 digests and the graph-description SHA-256, extracts only the named regular graph member, and
retains upstream license files. It never disables TLS verification or executes
downloaded Python/code. Setup uses the publisher's Google Storage HTTPS endpoint
because `download.tensorflow.org` did not present a matching HTTPS certificate.
Inference never downloads models or makes a network call.

Fixture licenses and transformations are listed in
[tests/fixtures/vision/ATTRIBUTION.md](../tests/fixtures/vision/ATTRIBUTION.md).
