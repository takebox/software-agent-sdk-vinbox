import { HttpClient } from './http-client';
import type {
  AgentServerAppBackendSessionResponse,
  AgentServerViczinBackendDataDeleteResponse,
  AgentServerViczinBackendLogsResponse,
  AgentServerViczinBackendPrepareResponse,
  AgentServerViczinBackendStartResponse,
  AgentServerViczinBackendStatusResponse,
  AgentServerViczinBackendStopResponse,
} from '../models/agent-server-api';

export interface ViczinExtensionsClientOptions {
  host: string;
  apiKey?: string;
  timeout?: number;
  appBackendIngressUrl?: string;
}

export class ViczinExtensionsClient {
  public readonly host: string;
  public readonly apiKey?: string;
  public readonly appBackendIngressUrl?: string;
  private readonly client: HttpClient;
  private readonly appBackendClient?: HttpClient;

  constructor(options: ViczinExtensionsClientOptions) {
    this.host = options.host.replace(/\/+$/, '');
    this.apiKey = options.apiKey;
    this.appBackendIngressUrl = options.appBackendIngressUrl?.replace(/\/+$/, '');
    const timeout = options.timeout || 60000;
    this.client = new HttpClient({
      baseUrl: this.host,
      apiKey: this.apiKey,
      timeout,
    });
    if (this.appBackendIngressUrl) {
      this.appBackendClient = new HttpClient({
        baseUrl: this.appBackendIngressUrl,
        apiKey: this.apiKey,
        timeout,
      });
    }
  }

  private backendPath(name: string, suffix = ''): string {
    return `/api/viczin-extensions/installed/${encodeURIComponent(name)}/backend${suffix}`;
  }

  async getBackendStatus(name: string): Promise<AgentServerViczinBackendStatusResponse> {
    const response = await this.client.get<AgentServerViczinBackendStatusResponse>(
      this.backendPath(name)
    );
    return response.data;
  }

  async prepareBackend(
    name: string,
    revision: string
  ): Promise<AgentServerViczinBackendPrepareResponse> {
    const response = await this.client.post<AgentServerViczinBackendPrepareResponse>(
      this.backendPath(name, '/prepare'),
      { revision }
    );
    return response.data;
  }

  async startBackend(
    name: string,
    revision: string
  ): Promise<AgentServerViczinBackendStartResponse> {
    const response = await this.client.post<AgentServerViczinBackendStartResponse>(
      this.backendPath(name, '/start'),
      { revision }
    );
    return response.data;
  }

  async stopBackend(name: string): Promise<AgentServerViczinBackendStopResponse> {
    const response = await this.client.post<AgentServerViczinBackendStopResponse>(
      this.backendPath(name, '/stop')
    );
    return response.data;
  }

  async getBackendLogs(
    name: string,
    limitBytes = 64 * 1024
  ): Promise<AgentServerViczinBackendLogsResponse> {
    const response = await this.client.get<AgentServerViczinBackendLogsResponse>(
      this.backendPath(name, '/logs'),
      { params: { limit_bytes: limitBytes } }
    );
    return response.data;
  }

  async deleteBackendData(name: string): Promise<AgentServerViczinBackendDataDeleteResponse> {
    const response = await this.client.delete<AgentServerViczinBackendDataDeleteResponse>(
      this.backendPath(name, '/data')
    );
    return response.data;
  }

  /**
   * Bootstrap an authenticated session for an app backend.
   *
   * `signal` is the caller's lifecycle signal (e.g. a React mount
   * `AbortController`); it is combined with the client timeout so teardown or a
   * retry cancels the in-flight bootstrap instead of letting it resolve into a
   * superseded consumer and revoke the session the live frame is using.
   */
  async createAppBackendSession(
    name: string,
    signal?: AbortSignal
  ): Promise<AgentServerAppBackendSessionResponse> {
    const client = this.requireAppBackendClient();
    const response = await client.post<AgentServerAppBackendSessionResponse>(
      `/app-backends/${encodeURIComponent(name)}/session`,
      undefined,
      { credentials: 'include', signal }
    );
    return response.data;
  }

  async revokeAppBackendSession(name: string, signal?: AbortSignal): Promise<void> {
    const client = this.requireAppBackendClient();
    await client.delete(`/app-backends/${encodeURIComponent(name)}/session`, {
      credentials: 'include',
      acceptableStatusCodes: new Set([204]),
      signal,
    });
  }

  private requireAppBackendClient(): HttpClient {
    if (!this.appBackendClient) {
      throw new Error(
        'Viczin App backend ingress is unavailable; use app_backend_ingress_url from /server_info'
      );
    }
    return this.appBackendClient;
  }

  close(): void {
    this.client.close();
    this.appBackendClient?.close();
  }
}
