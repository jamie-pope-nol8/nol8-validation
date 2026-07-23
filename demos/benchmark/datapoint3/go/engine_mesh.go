package main

// Real-engine agent-to-agent control for Data Point 3.
//
// The engine (NOL8/Themis :443 or RE2/Aergia :444) only does literal replacement, so
// the mesh policy (demos/policies/mesh.nol) maps every governed literal to a short
// sentinel. This mode calls the engine at EVERY control point of an agent workflow -
// each agent-to-agent handoff, the external tool call, and the final output - and
// derives the block/mask/route/tag action from which sentinel the engine emitted. The
// same policy runs on both engines, exactly like DP1 and DP2, so themis_api_mesh vs
// aergia_api_mesh is a like-for-like comparison.
//
// This mirrors datapoint2/go/engine_infer.go generalized from two control points to
// the full mesh, and reuses the DP3 EventRecord / SummaryStats / writeEvent / modelOutput
// machinery in main.go so the output is identical in shape to the sim modes.

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// EngineConfig points at one real engine's data plane.
type EngineConfig struct {
	Endpoint  string
	Token     string
	Timeout   time.Duration
	ModeLabel string
}

func loadEngineConfig(modeLabel, endpointEnv, tokenEnv string) (EngineConfig, error) {
	endpoint := strings.TrimSpace(os.Getenv(endpointEnv))
	if endpoint == "" {
		return EngineConfig{}, fmt.Errorf("%s is required for %s mode", endpointEnv, modeLabel)
	}
	timeout := 30 * time.Second
	if raw := strings.TrimSpace(os.Getenv("ENGINE_TIMEOUT_MS")); raw != "" {
		var ms int
		if _, err := fmt.Sscanf(raw, "%d", &ms); err == nil && ms > 0 {
			timeout = time.Duration(ms) * time.Millisecond
		}
	}
	return EngineConfig{
		Endpoint:  endpoint,
		Token:     strings.TrimSpace(os.Getenv(tokenEnv)),
		Timeout:   timeout,
		ModeLabel: modeLabel,
	}, nil
}

// callEngineProcess sends one string through the engine's literal redaction and
// returns the processed text (policy sentinels substituted in place).
func callEngineProcess(client *http.Client, cfg EngineConfig, text string) (string, error) {
	payload, err := json.Marshal(map[string]string{"message": text})
	if err != nil {
		return "", err
	}
	req, err := http.NewRequest(http.MethodPost, cfg.Endpoint, bytes.NewReader(payload))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	if cfg.Token != "" {
		req.Header.Set("Authorization", "Bearer "+cfg.Token)
	}
	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", fmt.Errorf("engine returned status %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	var parsed struct {
		Result struct {
			Message string `json:"message"`
		} `json:"result"`
	}
	if err := json.Unmarshal(body, &parsed); err != nil {
		return "", fmt.Errorf("decode engine response: %w", err)
	}
	return parsed.Result.Message, nil
}

// Sentinels emitted by demos/policies/mesh.nol.
const (
	meshBlockTool = "[BLOCK_TOOL]"
	meshBlockHand = "[BLOCK_HAND]"
	meshRoute     = "[ROUTE]"
	meshMaskCard  = "[MASK_CARD]"
	meshMaskAcct  = "[MASK_ACCT]"
	meshBlockOut  = "[BLOCK_OUT]"
	meshTagPriv   = "[TAG_PRIV]"
)

// maskAddedThisStage reports whether the engine introduced a NEW mask sentinel while
// processing this stage's input - i.e. a card/account literal was redacted here. A mask
// sentinel that was already present in the input (a value masked at an earlier hop and
// carried forward) does not count: masking is a governance action once, at the hop where
// the value is first redacted; downstream hops merely forward the already-masked message.
func maskAddedThisStage(input, processed string) bool {
	for _, s := range []string{meshMaskCard, meshMaskAcct} {
		if strings.Contains(processed, s) && !strings.Contains(input, s) {
			return true
		}
	}
	return false
}

// deriveHandoffAction maps the engine's processed handoff message to an action, in the
// same precedence as the listmesh mode: route (flagged/denied) > block_handoff
// (internal project) > mask (a card/account redacted at THIS hop) > allow.
func deriveHandoffAction(input, processed string) string {
	switch {
	case strings.Contains(processed, meshRoute):
		return "route"
	case strings.Contains(processed, meshBlockHand):
		return "block_handoff"
	case maskAddedThisStage(input, processed):
		return "mask"
	default:
		return "allow"
	}
}

// deriveToolAction maps the engine's processed tool-call text to an action.
func deriveToolAction(processed string) string {
	if strings.Contains(processed, meshBlockTool) {
		return "block_tool"
	}
	return "allow"
}

// deriveFinalAction maps the engine's processed final output to an action, mirroring
// listmesh: block (output-block) > tag (privileged) > mask (redacted at THIS stage) > allow.
func deriveFinalAction(input, processed string) (string, string) {
	switch {
	case strings.Contains(processed, meshBlockOut):
		return "block", "[BLOCKED_OUTPUT]"
	case strings.Contains(processed, meshTagPriv):
		return "tag", processed
	case maskAddedThisStage(input, processed):
		return "mask", processed
	default:
		return "allow", processed
	}
}

// runEngineMesh runs the full agent mesh through one real engine, governing every hop.
// It follows the exact flow of runMode (four handoffs -> tool -> final) but resolves
// each stage's action by calling the engine and reading the sentinels it emitted.
func runEngineMesh(tasks []TaskRecord, outputDir string, cfg EngineConfig) (SummaryStats, error) {
	start := time.Now()
	stats := SummaryStats{Mode: cfg.ModeLabel, TasksTotal: len(tasks)}

	if err := os.MkdirAll(outputDir, 0o755); err != nil {
		return stats, err
	}
	outPath := filepath.Join(outputDir, cfg.ModeLabel+"_events.jsonl")
	file, err := os.Create(outPath)
	if err != nil {
		return stats, err
	}
	defer file.Close()
	encoder := json.NewEncoder(file)

	client := &http.Client{Timeout: cfg.Timeout}

	stages := []struct {
		name   string
		source string
		target string
	}{
		{"triage", "user", "triage_agent"},
		{"research", "triage_agent", "research_agent"},
		{"decision", "research_agent", "decision_agent"},
		{"action", "decision_agent", "action_agent"},
	}

	callEngine := func(text string) (string, error) {
		s := time.Now()
		processed, err := callEngineProcess(client, cfg, text)
		stats.PreprocessMs += float64(time.Since(s).Microseconds()) / 1000.0
		return processed, err
	}

	for _, task := range tasks {
		text := task.UserTask

		meshStopped := false
		terminalBlocked := false
		meshAction := "allow"

		for _, stage := range stages {
			processed, err := callEngine(text)
			if err != nil {
				return stats, fmt.Errorf("task %s handoff %s: %w", task.TaskID, stage.name, err)
			}
			action := deriveHandoffAction(text, processed)
			if action != "allow" {
				meshAction = action
			}
			writeEvent(encoder, EventRecord{
				TaskID:        task.TaskID,
				Mode:          cfg.ModeLabel,
				Stage:         stage.name,
				EventType:     "agent_message",
				SourceAgent:   stage.source,
				TargetAgent:   stage.target,
				Action:        action,
				OriginalText:  text,
				ProcessedText: processed,
			}, &stats)
			text = processed
			// allow/mask forward the (possibly redacted) message to the next agent;
			// route/block_handoff stop it, so nothing is delivered downstream.
			if action == "allow" || action == "mask" {
				stats.DownstreamTokensDelivered += tokenEstimate(processed)
			}
			if action == "block_handoff" {
				meshStopped = true
				terminalBlocked = true
				break
			}
			if action == "route" {
				meshStopped = true
				break
			}
		}

		toolAction := "allow"
		if !meshStopped {
			processed, err := callEngine(text)
			if err != nil {
				return stats, fmt.Errorf("task %s tool: %w", task.TaskID, err)
			}
			toolAction = deriveToolAction(processed)
			writeEvent(encoder, EventRecord{
				TaskID:        task.TaskID,
				Mode:          cfg.ModeLabel,
				Stage:         "tool",
				EventType:     "tool_call",
				SourceAgent:   "action_agent",
				TargetAgent:   "external_tool",
				ToolName:      "external_send",
				Action:        toolAction,
				OriginalText:  text,
				ProcessedText: processed,
			}, &stats)
			if toolAction == "block_tool" {
				meshStopped = true
				terminalBlocked = true
				meshAction = "block_tool"
			} else {
				text = processed
				// an allowed tool call delivers its payload to the external tool.
				stats.DownstreamTokensDelivered += tokenEstimate(processed)
			}
		}

		finalText := modelOutput(task, text)
		finalAction := "block"
		finalProcessed := "[BLOCKED_OUTPUT]"
		if !terminalBlocked {
			processed, err := callEngine(finalText)
			if err != nil {
				return stats, fmt.Errorf("task %s final: %w", task.TaskID, err)
			}
			finalAction, finalProcessed = deriveFinalAction(finalText, processed)
		}
		// a delivered final response (allow/mask/tag) reaches the user; block delivers nothing.
		if finalAction != "block" {
			stats.DownstreamTokensDelivered += tokenEstimate(finalProcessed)
		}
		writeEvent(encoder, EventRecord{
			TaskID:        task.TaskID,
			Mode:          cfg.ModeLabel,
			Stage:         "final",
			EventType:     "final_output",
			SourceAgent:   "final_agent",
			TargetAgent:   "user",
			Action:        finalAction,
			OriginalText:  finalText,
			ProcessedText: finalProcessed,
		}, &stats)

		if meshAction == task.ExpectedMeshAction && finalAction == task.ExpectedFinalAction {
			stats.ContractAlignmentCount++
		}
	}

	elapsed := time.Since(start)
	if elapsed.Seconds() > 0 {
		stats.EventsPerSec = float64(stats.AgentMessagesTotal+stats.ToolCallsAttempted+stats.FinalOutputsTotal) / elapsed.Seconds()
	}
	return stats, nil
}
