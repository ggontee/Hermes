import * as fs from "node:fs";
import * as path from "node:path";
import * as cdk from "aws-cdk-lib";
import * as dlm from "aws-cdk-lib/aws-dlm";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as iam from "aws-cdk-lib/aws-iam";
import type { Construct } from "constructs";

export interface HermesStackProps extends cdk.StackProps {
  repoUrl: string;
}

const UBUNTU_ARM64 = "/aws/service/canonical/ubuntu/server/24.04/stable/current/arm64/hvm/ebs-gp3/ami-id";

/**
 * EC2 한 대. 인바운드 규칙이 없고, 접속은 Tailscale(평소)과 SSM Session Manager(비상)로만 한다.
 * 첫 부팅 스크립트는 deploy/bootstrap.sh 그대로다.
 */
export class HermesStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: HermesStackProps) {
    super(scope, id, props);

    const vpc = new ec2.Vpc(this, "Vpc", {
      ipAddresses: ec2.IpAddresses.cidr("10.42.0.0/24"),
      maxAzs: 1,
      natGateways: 0,
      subnetConfiguration: [{ name: "public", subnetType: ec2.SubnetType.PUBLIC, cidrMask: 26 }],
      restrictDefaultSecurityGroup: true,
    });

    const sg = new ec2.SecurityGroup(this, "Sg", {
      vpc,
      description: "Hermes: no inbound; outbound https/http/tailscale only",
      allowAllOutbound: false,
    });
    sg.addEgressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(443), "https (APIs, GitHub over 443, Tailscale DERP)");
    sg.addEgressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(80), "apt, RSS over http");
    sg.addEgressRule(ec2.Peer.anyIpv4(), ec2.Port.udp(41641), "Tailscale direct");
    sg.addEgressRule(ec2.Peer.anyIpv4(), ec2.Port.udp(3478), "Tailscale STUN");

    const role = new iam.Role(this, "Role", {
      assumedBy: new iam.ServicePrincipal("ec2.amazonaws.com"),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName("AmazonSSMManagedInstanceCore"),
        iam.ManagedPolicy.fromAwsManagedPolicyName("CloudWatchAgentServerPolicy"),
      ],
    });
    role.addToPolicy(
      new iam.PolicyStatement({
        actions: ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"],
        resources: [`arn:${this.partition}:secretsmanager:${this.region}:${this.account}:secret:hermes/*`],
      }),
    );

    // Tana 토큰은 분석 워커가 갱신한 뒤 다시 쓴다(refresh_token이 바뀔 수 있다).
    role.addToPolicy(
      new iam.PolicyStatement({
        actions: ["secretsmanager:PutSecretValue"],
        resources: [`arn:${this.partition}:secretsmanager:${this.region}:${this.account}:secret:hermes/tana-token-*`],
      }),
    );

    const bootstrap = fs
      .readFileSync(path.join(__dirname, "..", "..", "deploy", "bootstrap.sh"), "utf8")
      .replace("__REPO_URL__", props.repoUrl)
      .replace("__AWS_REGION__", this.region);
    const userData = ec2.UserData.custom(bootstrap);

    const instance = new ec2.Instance(this, "Server", {
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
      associatePublicIpAddress: true,
      instanceType: new ec2.InstanceType("t4g.small"),
      machineImage: ec2.MachineImage.fromSsmParameter(UBUNTU_ARM64, { os: ec2.OperatingSystemType.LINUX }),
      securityGroup: sg,
      role,
      userData,
      requireImdsv2: true,
      blockDevices: [
        { deviceName: "/dev/sda1", volume: ec2.BlockDeviceVolume.ebs(30, { volumeType: ec2.EbsDeviceVolumeType.GP3, encrypted: true }) },
      ],
    });
    cdk.Tags.of(instance).add("Name", "hermes");
    cdk.Tags.of(instance).add("hermes-backup", "daily");

    // EBS 스냅샷: 하루 1번, 7개 보관
    const dlmRole = new iam.Role(this, "DlmRole", {
      assumedBy: new iam.ServicePrincipal("dlm.amazonaws.com"),
      managedPolicies: [iam.ManagedPolicy.fromAwsManagedPolicyName("service-role/AWSDataLifecycleManagerServiceRole")],
    });
    new dlm.CfnLifecyclePolicy(this, "Snapshots", {
      description: "hermes daily snapshots keep 7",
      state: "ENABLED",
      executionRoleArn: dlmRole.roleArn,
      policyDetails: {
        resourceTypes: ["INSTANCE"],
        targetTags: [{ key: "hermes-backup", value: "daily" }],
        schedules: [
          {
            name: "daily",
            createRule: { interval: 24, intervalUnit: "HOURS", times: ["18:00"] }, // UTC 18:00 = KST 03:00
            retainRule: { count: 7 },
            copyTags: true,
          },
        ],
      },
    });

    new cdk.CfnOutput(this, "InstanceId", { value: instance.instanceId });
    new cdk.CfnOutput(this, "SsmSession", { value: `aws ssm start-session --target ${instance.instanceId} --region ${this.region}` });
  }
}
