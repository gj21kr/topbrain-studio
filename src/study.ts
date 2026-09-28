export interface StudyStep {
  structureId: string;
  title: string;
  instruction: string;
}

export interface StudyTrail {
  id: string;
  title: string;
  summary: string;
  steps: StudyStep[];
}

/** Guided interactions for the procedural teaching schematic only. */
export const demoTrails: StudyTrail[] = [
  {
    id: 'anterior-path',
    title: '앞쪽 경로 따라가기',
    summary: '예시 모식도의 앞쪽 경로를 선택과 단독 보기로 살펴봅니다. 실제 해부학적 주행이나 크기를 나타내지 않습니다.',
    steps: [
      { structureId: 'left-ica', title: '시작점 선택', instruction: '선택된 경로를 회전해 살펴본 뒤, 단독 보기를 켜서 예시 혈관선을 확인하세요.' },
      { structureId: 'left-mca', title: '바깥쪽 경로 보기', instruction: '단독 보기를 해제하고 주변 경로와 비교하세요. 다시 단독 보기로 이 분지만 살펴보세요.' },
      { structureId: 'left-aca', title: '가까운 경로 비교', instruction: '앞쪽 화면으로 돌아가 두 분지의 모식적 위치를 비교해 보세요.' },
    ],
  },
  {
    id: 'posterior-path',
    title: '뒤쪽 경로 회전하기',
    summary: '예시 모식도의 뒤쪽 경로를 여러 시점에서 관찰합니다. 환자별 혈관 형태를 뜻하지 않습니다.',
    steps: [
      { structureId: 'left-va', title: '아래쪽에서 시작', instruction: '모델을 돌려 뒤쪽 경로의 시작 부분을 찾아보세요.' },
      { structureId: 'basilar', title: '가운데 경로 찾기', instruction: '레이블을 켜고 가운데 경로를 선택한 다음, 단독 보기로 윤곽을 확인하세요.' },
      { structureId: 'left-pca', title: '위쪽 분지 보기', instruction: '단독 보기를 해제하고 위쪽 분지를 선택해 연결된 예시 경로를 살펴보세요.' },
    ],
  },
  {
    id: 'side-comparison',
    title: '좌우 예시 비교하기',
    summary: '오른쪽 경로를 차례로 선택하며 왼쪽의 대응 위치와 비교합니다. 대칭 모식도이며 실제 개인차를 반영하지 않습니다.',
    steps: [
      { structureId: 'right-ica', title: '반대쪽 시작점', instruction: '왼쪽 대응 구조와 함께 보이도록 단독 보기를 끄고 화면을 회전해 비교하세요.' },
      { structureId: 'right-mca', title: '바깥쪽 짝 비교', instruction: '주변 투명도를 낮춰 두 쪽의 예시 경로를 구분해 보세요.' },
      { structureId: 'right-aca', title: '원래 위치로 되돌리기', instruction: '구조 분해 슬라이더를 움직여 본 뒤 조립 상태로 되돌려 위치를 비교하세요.' },
    ],
  },
];
