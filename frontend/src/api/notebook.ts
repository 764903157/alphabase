import axios from "axios";

const client = axios.create({ baseURL: "/api/notebook" });

export interface CellResult {
  type: "dataframe" | "text" | "error" | "chart";
  data: any;
  shape?: [number, number];
  columns?: string[];
  stdout: string;
}

export interface Session {
  id: number;
  name: string;
  cells: CellData[];
  created_at: string;
  updated_at: string;
}

export interface CellData {
  id: string;
  type: "code";
  code: string;
  result?: CellResult;
}

export const notebookApi = {
  execute: (code: string) =>
    client.post<CellResult>("/execute", { code }),

  listSessions: () =>
    client.get<{ data: Session[] }>("/sessions"),

  createSession: (name: string) =>
    client.post<{ id: number; name: string }>("/sessions", null, {
      params: { name },
    }),

  getSession: (id: number) =>
    client.get<Session>(`/sessions/${id}`),

  saveSession: (id: number, data: { name?: string; cells?: CellData[] }) =>
    client.put(`/sessions/${id}`, null, { params: data as any }),

  deleteSession: (id: number) =>
    client.delete(`/sessions/${id}`),
};