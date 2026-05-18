import axios from "axios";

const client = axios.create({ baseURL: "/api/data" });

export const dataApi = {
  getKline: (params: {
    code: string;
    freq?: string;
    start?: string;
    end?: string;
    limit?: number;
    adjust?: string;
  }) => client.get<{ code: string; data: any[]; total: number }>("/kline", { params }),

  getStocks: () =>
    client.get<{ data: { code: string; name: string }[] }>("/stocks"),

  saveKline: (params: {
    code: string;
    freq?: string;
    start?: string;
    end?: string;
    adjust?: string;
  }) => client.post("/kline/save", params),
};