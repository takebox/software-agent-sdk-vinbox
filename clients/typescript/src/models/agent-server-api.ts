/**
 * Stable public aliases for selected generated Agent Server operations.
 *
 * Keep generator-specific lookup names in this file instead of spreading them
 * through the handwritten client.
 */
import type {
  GetAgentSettingsSchemaApiSettingsAgentSchemaGetResponse,
  GetConversationSettingsSchemaApiSettingsConversationSchemaGetResponse,
  GetMcpOauthStatusApiMcpOauthStatusJobIdGetResponse,
  GetSettingsApiSettingsGetResponse,
  McpToolCallSpec,
  McpToolCallResult,
  StartMcpOauthApiMcpOauthStartPostData,
  StartMcpOauthApiMcpOauthStartPostResponse,
  SubmitMcpOauthCallbackApiMcpOauthCallbackJobIdPostData,
  SubmitMcpOauthCallbackApiMcpOauthCallbackJobIdPostResponse,
  TestMcpServerApiMcpTestPostData,
  TestMcpServerApiMcpTestPostResponse,
  UpdateSettingsApiSettingsPatchData,
  UpdateSettingsApiSettingsPatchResponse,
} from '../generated/agent-server-schema';

export type AgentServerSettingsSchema = GetAgentSettingsSchemaApiSettingsAgentSchemaGetResponse;
export type AgentServerConversationSettingsSchema =
  GetConversationSettingsSchemaApiSettingsConversationSchemaGetResponse;
export type AgentServerSettingsResponse = GetSettingsApiSettingsGetResponse;
export type AgentServerSettingsPatchRequest = UpdateSettingsApiSettingsPatchData['body'];
export type AgentServerSettingsPatchResponse = UpdateSettingsApiSettingsPatchResponse;

export type AgentServerMCPTestRequest = TestMcpServerApiMcpTestPostData['body'];
export type AgentServerMCPTestResponse = TestMcpServerApiMcpTestPostResponse;
export type AgentServerMCPToolCall = McpToolCallSpec;
export type AgentServerMCPStartOAuthRequest = StartMcpOauthApiMcpOauthStartPostData['body'];
export type AgentServerMCPStartOAuthResponse = StartMcpOauthApiMcpOauthStartPostResponse;
export type AgentServerMCPOAuthStatusResponse = GetMcpOauthStatusApiMcpOauthStatusJobIdGetResponse;
export type AgentServerMCPOAuthCallbackRequest =
  SubmitMcpOauthCallbackApiMcpOauthCallbackJobIdPostData['body'];
export type AgentServerMCPOAuthCallbackResponse =
  SubmitMcpOauthCallbackApiMcpOauthCallbackJobIdPostResponse;
export type AgentServerMCPToolCallResult = McpToolCallResult;

export interface AgentServerViczinBackendRevisionRequest {
  revision: string;
}

export type AgentServerViczinBackendState =
  'missing' | 'stopped' | 'starting' | 'ready' | 'unhealthy' | 'unsupported';

export interface AgentServerViczinBackendStatus {
  name: string;
  state: AgentServerViczinBackendState;
  revision?: string | null;
  prepared_revision?: string | null;
  pid?: number | null;
  port?: number | null;
  detail?: string | null;
}

export interface AgentServerViczinBackendLogs {
  name: string;
  logs: string;
  truncated: boolean;
}

export type AgentServerViczinBackendStatusResponse = AgentServerViczinBackendStatus;
export type AgentServerViczinBackendPrepareResponse = AgentServerViczinBackendStatus;
export type AgentServerViczinBackendStartResponse = AgentServerViczinBackendStatus;
export type AgentServerViczinBackendStopResponse = AgentServerViczinBackendStatus;
export type AgentServerViczinBackendDataDeleteResponse = AgentServerViczinBackendStatus;
export type AgentServerViczinBackendLogsResponse = AgentServerViczinBackendLogs;

export interface AgentServerAppBackendSession {
  ingress_url: string;
  expires_at: string;
  iframe_sandbox: string;
}

export type AgentServerAppBackendSessionResponse = AgentServerAppBackendSession;
