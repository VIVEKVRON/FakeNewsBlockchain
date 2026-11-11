const hre = require("hardhat");
const fs = require("fs");
const path = require("path");

async function main() {
  console.log("--------------------------------------------------");
  console.log("Deploying VerificationRegistry Smart Contract...");
  console.log("Target Network:", hre.network.name);
  console.log("--------------------------------------------------");

  const [deployer] = await hre.ethers.getSigners();
  console.log("Deployer Address:", deployer.address);
  const balance = await hre.ethers.provider.getBalance(deployer.address);
  console.log("Deployer Balance:", hre.ethers.formatEther(balance), "ETH");

  const VerificationRegistry = await hre.ethers.getContractFactory("VerificationRegistry");
  const registry = await VerificationRegistry.deploy();

  const deployTx = registry.deploymentTransaction();
  const txHash = deployTx ? deployTx.hash : null;
  console.log("Deployment Transaction Submitted. Hash:", txHash);

  await registry.waitForDeployment();
  const contractAddress = await registry.getAddress();

  console.log("--------------------------------------------------");
  console.log("SUCCESS: VerificationRegistry deployed to:", contractAddress);
  console.log("Deployment Transaction Hash:", txHash);
  if (hre.network.name === "sepolia") {
    console.log("Etherscan Deployment Link: https://sepolia.etherscan.io/tx/" + txHash);
    console.log("Etherscan Contract Link: https://sepolia.etherscan.io/address/" + contractAddress);
  }
  console.log("Owner:", await registry.owner());
  console.log("Paused status:", await registry.paused());
  console.log("--------------------------------------------------");

  // Save deployment metadata to a local JSON file for backend consumption
  const deploymentInfo = {
    network: hre.network.name,
    chainId: (await hre.ethers.provider.getNetwork()).chainId.toString(),
    contractAddress: contractAddress,
    transactionHash: txHash,
    deployerAddress: deployer.address,
    deployedAt: new Date().toISOString()
  };

  const deploymentsDir = path.join(__dirname, "..", "deployments");
  if (!fs.existsSync(deploymentsDir)) {
    fs.mkdirSync(deploymentsDir, { recursive: true });
  }

  const outputPath = path.join(deploymentsDir, `${hre.network.name}-deployment.json`);
  fs.writeFileSync(outputPath, JSON.stringify(deploymentInfo, null, 2));
  console.log(`Deployment info saved to: ${outputPath}`);
}

main().catch((error) => {
  console.error("Deployment failed:", error);
  process.exitCode = 1;
});
