export const isWebId = (id: string) => /^w[0-9a-f]{20}$/.test(id);
export const isUserId = (id: string) => /^(\d{5,25}|w[0-9a-f]{20})$/.test(id);
