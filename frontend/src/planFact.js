export const PLAN_FACT_GROUPS = [
  { name: "SA", children: ["Мой"] },
  { name: "Карты", children: [] },
  { name: "Устройства", children: [] },
  { name: "Saima", children: [] },
  { name: "Телефоны", children: [] },
  { name: "Аксессуары", children: [] },
  { name: "Вместе дешевле", children: [] },
  { name: "O!семья", children: [] },
];

export const PLAN_FACT_ITEMS = PLAN_FACT_GROUPS.flatMap(({ name, children }) => [
  { name, parent: null },
  ...children.map((child) => ({ name: child, parent: name })),
]);

export const PLAN_FACT_DEFAULTS = {
  SA: { metric: "quantity", goal: 30 },
  Мой: { metric: "quantity", goal: 25 },
  Карты: { metric: "quantity", goal: 25 },
  Устройства: { metric: "quantity", goal: 2 },
  Saima: { metric: "quantity", goal: 1 },
  Телефоны: { metric: "quantity", goal: 2 },
  Аксессуары: { metric: "revenue", goal: 3100 },
  "Вместе дешевле": { metric: "quantity", goal: 0 },
  "O!семья": { metric: "quantity", goal: 0 },
};
