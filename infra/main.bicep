// Pitchside on Azure Container Apps.
// Uses an existing Microsoft Foundry resource for the models (created in the Foundry portal).

targetScope = 'resourceGroup'

@description('Name prefix for every resource.')
param name string = 'pitchside'

@description('Azure region. Azure for Students subscriptions only allow a few; Poland Central has the models we use.')
param location string = resourceGroup().location

@description('Azure OpenAI endpoint of the Foundry resource, for example https://<resource>.openai.azure.com/')
param openAiEndpoint string

@description('Model deployment the agents use.')
param openAiDeployment string = 'gpt-4.1-mini'

@secure()
@description('API key of the Foundry resource. Stored as a Container Apps secret, never in the image.')
param openAiKey string

@description('Region for Azure AI Speech (not offered in every region; East Asia is on the student allow-list).')
param speechLocation string = 'eastasia'

@description('Container image. azd sets this on deploy; the placeholder lets the first provision succeed.')
param image string = 'mcr.microsoft.com/k8se/quickstart:latest'

var suffix = uniqueString(resourceGroup().id)
var tags = { 'azd-env-name': name, project: 'pitchside' }

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${name}-logs-${suffix}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${name}-insights-${suffix}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

// Neural voices for spoken commentary in English, Hindi and Spanish. F0 is the free tier.
resource speech 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: '${name}-speech'
  location: speechLocation
  tags: tags
  kind: 'SpeechServices'
  sku: { name: 'F0' }
  properties: {}
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: replace('${name}acr${suffix}', '-', '')
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: true }
}

// A standard environment with the Consumption profile. (Without workloadProfiles, new subscriptions may
// get an "express" environment, which cannot pull from a private registry.)
resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${name}-cae-${suffix}'
  location: location
  tags: tags
  properties: {
    workloadProfiles: [
      { name: 'Consumption', workloadProfileType: 'Consumption' }
    ]
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${name}-web'
  location: location
  tags: union(tags, { 'azd-service-name': 'web' })
  properties: {
    managedEnvironmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        {
          server: registry.properties.loginServer
          username: registry.listCredentials().username
          passwordSecretRef: 'registry-password'
        }
      ]
      secrets: [
        { name: 'registry-password', value: registry.listCredentials().passwords[0].value }
        { name: 'openai-key', value: openAiKey }
        { name: 'appinsights', value: insights.properties.ConnectionString }
        { name: 'speech-key', value: speech.listKeys().key1 }
      ]
    }
    template: {
      containers: [
        {
          name: 'web'
          image: image
          resources: { cpu: json('1.0'), memory: '2Gi' }
          env: [
            { name: 'PORT', value: '8000' }
            { name: 'PITCHSIDE_PROVIDER', value: 'azure_openai' }
            { name: 'AZURE_OPENAI_ENDPOINT', value: openAiEndpoint }
            { name: 'AZURE_OPENAI_DEPLOYMENT', value: openAiDeployment }
            { name: 'AZURE_OPENAI_API_KEY', secretRef: 'openai-key' }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'appinsights' }
            { name: 'AZURE_SPEECH_KEY', secretRef: 'speech-key' }
            { name: 'AZURE_SPEECH_REGION', value: speechLocation }
          ]
          probes: [
            {
              type: 'Readiness'
              httpGet: { path: '/api/health', port: 8000 }
              initialDelaySeconds: 5
              periodSeconds: 10
            }
          ]
        }
      ]
      // Scale to zero when nobody is watching; one replica handles a few live matches.
      scale: { minReplicas: 0, maxReplicas: 2 }
    }
  }
}

output AZURE_CONTAINER_REGISTRY_ENDPOINT string = registry.properties.loginServer
output SERVICE_WEB_NAME string = app.name
output WEB_URL string = 'https://${app.properties.configuration.ingress.fqdn}'
output APPLICATIONINSIGHTS_NAME string = insights.name
