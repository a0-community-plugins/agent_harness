export default async function registerAgentHarnessSurface(surfaces) {
  surfaces.registerSurface({
    id: "agent-harness",
    title: "Harness",
    icon: "conversion_path",
    order: 35,
    modalPath: "/plugins/agent_harness/webui/main.html",
  });
}
