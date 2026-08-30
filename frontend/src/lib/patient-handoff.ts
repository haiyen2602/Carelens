export type PatientHandoffMessage = {
  id: string;
  senderRole: "PATIENT" | "DOCTOR" | "SYSTEM";
  content: string;
  createdAt: string;
};

export type PatientHandoff = {
  hasActiveHandoff: boolean;
  handoffId: string | null;
  status: string | null;
  messages: PatientHandoffMessage[];
};

type ApiHandoff = {
  has_active_handoff: boolean;
  handoff_id: string | null;
  status: string | null;
  messages: Array<{
    id: string;
    sender_role: PatientHandoffMessage["senderRole"];
    content: string;
    created_at: string;
  }>;
};

function headers(accessToken?: string | null): HeadersInit {
  return accessToken ? { Authorization: `Bearer ${accessToken}` } : {};
}

async function toHandoff(response: Response): Promise<PatientHandoff> {
  const body = (await response.json().catch(() => null)) as ApiHandoff | null;
  if (!response.ok || !body) throw new Error("Không thể tải cuộc trò chuyện với bác sĩ.");
  return {
    hasActiveHandoff: body.has_active_handoff,
    handoffId: body.handoff_id,
    status: body.status,
    messages: body.messages.map((message) => ({
      id: message.id,
      senderRole: message.sender_role,
      content: message.content,
      createdAt: message.created_at,
    })),
  };
}

export async function getPatientHandoff(
  patientId: string,
  accessToken?: string | null,
): Promise<PatientHandoff> {
  return toHandoff(
    await fetch(`/api/patient/handoff?patient_id=${encodeURIComponent(patientId)}`, {
      headers: headers(accessToken),
    }),
  );
}

export async function getPatientHandoffDetail(
  handoffId: string,
  accessToken?: string | null,
): Promise<PatientHandoff> {
  return toHandoff(
    await fetch(`/api/patient/handoff/${encodeURIComponent(handoffId)}`, {
      headers: headers(accessToken),
    }),
  );
}

export async function stopPatientHandoff(
  handoffId: string,
  accessToken?: string | null,
): Promise<PatientHandoff> {
  return toHandoff(
    await fetch(`/api/patient/handoff/${encodeURIComponent(handoffId)}/stop`, {
      method: "POST",
      headers: headers(accessToken),
    }),
  );
}
