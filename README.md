# Splatomy

공개 CT 데이터셋에서 해부 구조를 3D로 꺼내 브라우저에서 탐색하는 개인 프로젝트입니다. Python 변환기가 [TotalSegmentator 데이터셋](https://doi.org/10.5281/zenodo.10047292)(CC BY 4.0)의 한 피험자 — CT 한 장과 117개 구조의 ground-truth 분할 — 를 임베디드 GLB와 JSON manifest로 바꾸고, 같은 CT의 강도를 Gaussian splat **맥락 레이어**로 만들어 메시와 같은 좌표계에 깔며, three.js + [Spark](https://sparkjs.dev) 뷰어가 둘을 함께 읽습니다. 구조 검색, 그룹별 표시·투명도, 단독 보기, 카메라 프리셋, 분해(explode), 라벨, CT 맥락 on/off·농도를 제공합니다.

첫 화면의 혈관 모식도는 코드로 그린 도식이고, 실제 해부학은 변환한 데이터를 열었을 때만 나타납니다. 이 도구는 진단 기기가 아닙니다.

## 이 저장소가 보여주는 것

- **의료영상 좌표계를 끝까지 추적한다.** voxel → NIfTI affine → RAS mm → glTF metres. 회전·shear·비등방 spacing·좌우 반전(LAS) 볼륨을 전부 처리하고, 구조마다 voxel/vertex 한 쌍을 manifest에 남겨 독립 검산이 가능합니다.
- **언어 경계를 건너는 계약을 양쪽에서 강제한다.** GLB 상한(150 MB, 메시당 정점 3,000,000·인덱스 9,000,000), chunk 레이아웃, "schema 2면 모든 구조가 자기 출처를 가진다"는 규칙이 Python 변환기와 TypeScript 뷰어에 각각 구현돼 있고, Python 테스트가 `src/model.ts`를 직접 읽어 두 숫자가 같은지 대조합니다. 한쪽만 바꾸면 CI가 깨집니다.
- **테스트가 무엇을 검증하는지 뮤테이션으로 확인했다.** 상수를 바꾸거나 분기를 지웠을 때 실제로 실패하는 테스트만 남겼습니다. 이 과정에서 "통과하지만 아무것도 검증하지 않는" 테스트 네 개를 찾아 고쳤습니다.
- **분할 경계와 원본 CT를 한 좌표계에 겹친다.** 메시는 분할이 *어디서 끝나는지*를, splat 레이어는 그 경계가 *어떤 조직 속에 앉아 있는지*를 보여줍니다. 복셀당 Gaussian 하나를 학습 없이 볼륨에서 직접 초기화하고(뼈·조영 혈관·연조직의 HU 전달함수), 뷰어는 PLY 헤더의 splat 수, CT 체크섬, voxel→glTF 행렬이 GLB manifest와 일치할 때만 레이어를 받습니다. 다른 피험자·다른 좌표계의 레이어는 열리지 않습니다.
- **데이터는 저장소에 없다.** 코드만 배포하고, 데이터셋은 Zenodo에서 직접 받아 로컬에서 변환합니다. 파생 에셋은 `private-assets/`에 두고 커밋하지 않습니다.

## 데이터셋

Wasserthal, J. et al. *TotalSegmentator: Robust Segmentation of 104 Anatomic Structures in CT Images.* Radiology: AI 5(5), 2023. [doi:10.1148/ryai.230024](https://doi.org/10.1148/ryai.230024)
데이터: [Zenodo 10047292](https://doi.org/10.5281/zenodo.10047292) (v2.0.1, 1,228명, 117구조, 23.6 GB) · 탐색용 [소형판 10047263](https://doi.org/10.5281/zenodo.10047263) (102명, 3.2 GB). 라이선스 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

각 피험자 폴더는 `ct.nii.gz`와 `segmentations/<structure>.nii.gz`(구조별 0/1 마스크)로 구성됩니다. 변환기는 이 레이아웃을 그대로 읽습니다.

## 실행

Node.js 22 이상:

```bash
npm ci
npm run dev          # http://127.0.0.1:5181
npm test             # 뷰어 쪽 계약 검증
npm run build        # tsc + vite
```

Python 3.12–3.14 (`requirements-data.txt`가 핀한 numpy 2.5.x가 요구):

```bash
pip install -r requirements-data.txt
python -m unittest discover -s tests -t .
```

## 변환

Zenodo에서 받은 zip을 풀고 피험자 폴더 하나를 지정합니다.

```bash
python scripts/convert_subject.py --subject /path/to/Totalsegmentator_dataset_small_v201/s0011 --output private-assets/local-case
```

`private-assets/local-case.glb`와 `.json`이 생기면 앱의 **Open local case**가 로드합니다(개발/preview 서버가 loopback에만 그 경로들을 제공합니다). 다른 파일은 **Import GLB + manifest**로 브라우저 메모리에서 직접 엽니다.

같은 피험자의 CT 맥락 레이어는 두 번째 스크립트가 같은 출력 stem에 붙입니다.

```bash
python scripts/splat_context.py --subject /path/to/Totalsegmentator_dataset_small_v201/s0011 --output private-assets/local-case
```

`local-case.context.ply`(3DGS 레이아웃의 PLY)와 `.context.json`이 생기면 **Open local case**가 레이어까지 함께 열고, 가져오기에서는 GLB + manifest + PLY + context JSON 네 파일을 한 번에 선택합니다. 레이어는 선택 사항입니다. 전신 CT 한 명은 약 170만 splat·90 MB, 상한은 2,000,000입니다. 파이프라인과 좌표 계약의 상세는 [docs/DATA.md](docs/DATA.md)에 있습니다.

## 구성

```
scripts/convert_subject.py   NIfTI → GLB + manifest. 좌표 변환, marching cubes, GLB 검증, 구조 카탈로그
scripts/splat_context.py     CT → Gaussian splat PLY + context JSON. HU 전달함수, 복셀 프레임의 Gaussian, PLY 검증
src/model.ts                 manifest·context 검증, GLB·PLY 사전 검사, 뷰어 상태
src/Viewer.tsx               three.js 씬, 로더, Spark splat 레이어, 분해 애니메이션
src/App.tsx                  탐색 UI
tests/                       Python 37 · TypeScript 13 (전부 합성 fixture)
.github/workflows/ci.yml     Python 3.12·3.14 + Node 22
```

## 다음

- **splat 레이어의 학습.** 지금의 레이어는 복셀 초기화 그대로입니다(Gaussian 하나 = 복셀 하나, 크기는 복셀 반폭). 렌더 손실로 위치·크기·불투명도를 몇 단계 최적화하면 같은 화질을 훨씬 적은 splat으로 낼 수 있고, 그때는 원본 복셀 대비 오차를 context JSON에 기록합니다.
- **측정된 단순화.** 1.5 mm 격자의 marching cubes 출력은 계단 모양이 남고, 조밀한 구조는 뷰어의 메시당 상한에 닿습니다. 스무딩·decimation을 허용하되 원본 복셀과의 거리를 측정해 manifest에 기록합니다.

## 독립성

[Model X Studio](https://github.com/ashemag/model-x-studio)의 부품 탐색 UI에서 영감을 받은 독립 구현이며, 그 저장소의 코드나 모델은 포함하지 않습니다.
