DOMINANCIA CONTROLLER MOBILE - TERMUX

Como instalar no Termux:

1. Extraia o zip no celular.
2. Abra o Termux na pasta extraida.
3. Rode:

   sh instalar-termux.sh

4. Abra:

   ./dominancia-buyer

Atualizacao por Git:

Depois que o projeto estiver em um repositorio Git, rode:

   sh update-from-git.sh https://github.com/USUARIO/REPO.git

Se a pasta ja existir, ele atualiza/substitui os arquivos antigos e preserva:

- config.json
- .tamblox_device
- .env

Para atualizar de novo depois:

   cd ~/dominancia-controller-mobile
   sh update-from-git.sh https://github.com/USUARIO/REPO.git

Fluxo:

- O controller mobile usa apenas Tamblox.
- O app pede a license key.
- O servidor Cloudflare valida a licenca Tamblox.
- Depois de validar, proxy_url e license key ficam salvos no config.json desse celular.
- Na primeira validacao, o app cria um arquivo local chamado .tamblox_device.
- A licenca fica vinculada a esse dispositivo no servidor.
- Se a API key da Tamblox ainda nao estiver cadastrada nessa licenca, o app pede uma vez.
- A API key da Tamblox nao fica salva no celular; ela e registrada no servidor.
- Depois disso, requests e posts passam pelo Cloudflare.

Importante:

- Nao copie o arquivo .tamblox_device entre celulares.
- Se apagar .tamblox_device depois que a licenca ja foi registrada, essa licenca nao vai validar nesse aparelho ate o admin resetar o dispositivo no servidor.
- Uma licenca registrada em um celular nao funciona em outro, a menos que o admin resete o dispositivo no servidor.
- Nao coloque ADMIN_TOKEN nem secrets do Cloudflare neste pacote.
