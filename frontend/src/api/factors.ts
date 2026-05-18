import axios from "axios";

const client = axios.create({ baseURL: "/api/factors" });

export const factorsApi = {
  list: () => client.get("/list"),
  compute: (params: { code: string; factor_name: string; freq?: string }) =>
    client.post("/compute", params),
  delete: (id: number) => client.delete(`/${id}`),
};