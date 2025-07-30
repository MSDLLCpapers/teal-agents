# Phase 5 - Authorization Overview

This document provides an overview of how the new authorization system will work for
Teal Agents. Initially, it will only focus on OAuth 2.0, the design should be extensible
to support other authorization types in the future.

## Overview

The existing auth setup for teal agents is rudimentary and not scalable. As such, we
will refactor and include the ability for the platform to dynamically understand the
auth requirements for a particular tool and, when required, prompt the calling client
to prompt the user to perform the appropriate authorization flow. We will begin with
OAuth 2.0. The internal flow will go something like:

1.  Agent decides to use a tool
2.  Agent platform intercepts tool call response from LLM and retrieves the tool
    metadata from the tool catalog (see phase 4)
3.  If the tool requires authorization (for now, OAuth 2.0), the platform will search
    for an existing token for the given authorization server and scopes for this user
    within the "Secure Auth Storage Service"
4.  If the token exists, it will be used to invoke the tool
5.  If the token does not exist, a new response type will be crafted and returned that
    indicates to the client that the user needs to perform the appropriate authorization
    flow. Note that the flow must be initiated from the agent platform (or possibly
    directly to the authorization server but the callback must be the agent platform).
6.  The client will then prompt the user to perform the authorization flow, which will
    involve redirecting the user to the authorization server, where they will log in and
    authorize the tool. The client must also present an option to "Resume" the flow once
    authorization has been completed.
7.  Once the user has authorized the tool, the authorization server will redirect the
    user back to the agent platform with an authorization code. The agent platform will
    then exchange this code for an access token and store it in the "Secure Auth Storage
    Service" for future use.
8.  The agent platform will show a message indicating that authorization is complete and
    the user can now close this window/tab and resume the agent flow.
9.  The user returns to the original client and clicks "Resume" to continue the agent 
    flow.
10. The agent platform will resume the flow, now able to retrieve the appropriate access
    token from the "Secure Auth Storage Service" and invoke the tool.

## Implementation Aspects in Previous Phases

Many changes are required to accommodate this new authorization flow. Some of the work
has already been scoped, in previous phases:

### Phase 1
* Implementation plan defined in
  @planning/2507-state-hitl-auth/01-02-state-refactor-implementation-plan.md
* Integrates the concept of State in to the Agent Platform, which is what will allow
  individual agent flows to be paused and resumed.

### Phase 2
* Implementation plan defined in
  @planning/2507-state-hitl-auth/02-02-manual-tool-call-implementation-plan.md
* Implements the ability for the agent platform to intercept tool calls and provides a
  hook for tool evaluation prior to execution of the tool.

### Phase 3
* Implementation plan defined in
  @planning/2507-state-hitl-auth/03-03-hitl-implementation-plan.md
* Introduces a "resume" endpoint that allows the client to resume an agent flow
  after a HITL intervention. This is essential for the authorization flow, as it should
  be extended to additionally support the resumption of the agent flow after the
  authorization flow has been completed.

### Phase 4
* Implementation plan defined in
  @planning/2507-state-hitl-auth/04-02-tool-catalog-implementation-plan.md
* Implements the tool catalog, which is where the agent platform will retrieve the
  tool metadata to determine if authorization is required and, if so, provide the
  relevant details to craft the appropriate response to the client.

## Remaining Work

Upon completion of phases 1-4, agent task state should be available. We should have the
ability to intercept tool calls and evaluate them, and we should have a tool catalog
which contains the appropriate metadata for each tool. To introduce tool authorization,
we still need to implement the following:
1. The ability to store and retrieve the required tool authorization information for a
   given user and tool.
2. The ability to craft and send an appropriate response to the client when a tool
   requires authorization and for which no appropriate authorization information is
   available.
3. The ability to either initiate the authorization flow from the agent platform or
   simply receive the callback from the authorization server, retrieve/store the needed
   authorization information, and inform the user that the agent flow can be resumed.
4. The ability to resume the agent flow once the user has completed the authorization
   flow and returned to the client.