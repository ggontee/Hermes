#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { HermesStack } from "../lib/hermes-stack";

const app = new cdk.App();
new HermesStack(app, "Hermes", {
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: "ap-northeast-2" },
  description: "Hermes: 개인용 해외 인물 피드 (EC2 1대, Tailscale 전용, 인바운드 없음)",
  repoUrl: app.node.tryGetContext("repoUrl") ?? "git@github.com:ggontee/Hermes.git",
});
cdk.Tags.of(app).add("project", "hermes");
