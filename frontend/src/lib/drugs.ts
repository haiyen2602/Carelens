export type Drug = {
  id: string;
  name: string;
  category: string;
  defaultDose: string;
};

// Mock — thay bằng API tra cứu thuốc thật khi có database.
export const DRUG_DATABASE: Drug[] = [
  { id: "d1", name: "Amlodipine 5mg", category: "Hạ huyết áp", defaultDose: "1 viên" },
  { id: "d2", name: "Amlodipine 10mg", category: "Hạ huyết áp", defaultDose: "1 viên" },
  { id: "d3", name: "Losartan 50mg", category: "Hạ huyết áp", defaultDose: "1 viên" },
  { id: "d4", name: "Metformin 500mg", category: "Đái tháo đường", defaultDose: "1 viên" },
  { id: "d5", name: "Metformin 850mg", category: "Đái tháo đường", defaultDose: "1 viên" },
  {
    id: "d6",
    name: "Insulin Glargine (Lantus)",
    category: "Đái tháo đường",
    defaultDose: "10 đơn vị",
  },
  { id: "d7", name: "Atorvastatin 20mg", category: "Rối loạn mỡ máu", defaultDose: "1 viên" },
  { id: "d8", name: "Rosuvastatin 10mg", category: "Rối loạn mỡ máu", defaultDose: "1 viên" },
  {
    id: "d9",
    name: "Aspirin 81mg",
    category: "Chống đông / kháng tiểu cầu",
    defaultDose: "1 viên",
  },
  {
    id: "d10",
    name: "Clopidogrel 75mg",
    category: "Chống đông / kháng tiểu cầu",
    defaultDose: "1 viên",
  },
  { id: "d11", name: "Paracetamol 500mg", category: "Giảm đau, hạ sốt", defaultDose: "1-2 viên" },
  { id: "d12", name: "Ibuprofen 400mg", category: "Giảm đau, kháng viêm", defaultDose: "1 viên" },
  { id: "d13", name: "Omeprazole 20mg", category: "Dạ dày", defaultDose: "1 viên" },
  { id: "d14", name: "Salbutamol xịt 100mcg", category: "Hô hấp", defaultDose: "2 nhát xịt" },
  {
    id: "d15",
    name: "Vitamin D3 1000IU",
    category: "Vitamin & khoáng chất",
    defaultDose: "1 viên",
  },
  { id: "d16", name: "Levothyroxine 50mcg", category: "Tuyến giáp", defaultDose: "1 viên" },
  { id: "d17", name: "Furosemide 40mg", category: "Lợi tiểu", defaultDose: "1 viên" },
  { id: "d18", name: "Sertraline 50mg", category: "Thần kinh - tâm thần", defaultDose: "1 viên" },
];
