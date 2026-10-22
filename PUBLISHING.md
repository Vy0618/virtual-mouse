# Publicar no GitHub / Publishing to GitHub

## Português

Os arquivos estão preparados para um repositório GitHub. A configuração de CI
executará testes em Python 3.10, 3.12 e 3.14, incluindo X11 virtual, e verificará
o pacote Python. Isso não publica o projeto automaticamente.

1. Defina a licença de distribuição e adicione o arquivo `LICENSE` correspondente.
2. Crie um repositório vazio no GitHub, sem gerar README, licença ou `.gitignore`.
3. Na pasta do projeto, revise e faça o primeiro commit:

   ```bash
   git status --short
   git add .
   git diff --cached --stat
   git commit -m "Initial commit"
   ```

4. Substitua `SEU_USUARIO` pelo seu usuário e configure o remoto:

   ```bash
   git remote add origin git@github.com:SEU_USUARIO/virtual_mouse.git
   git push -u origin main
   ```

O exemplo usa autenticação SSH. Se preferir HTTPS, copie a URL oferecida pelo
GitHub. Acompanhe a primeira execução na aba **Actions**.

O `.gitignore` mantém caches, ambientes virtuais, credenciais e configurações
locais fora do commit; os arquivos `config.example.json` e `i3.conf.example`
continuam disponíveis para publicação.

## English

The files are ready for a GitHub repository. CI will run tests on Python 3.10,
3.12, and 3.14, including virtual X11, and verify the Python package. This does
not publish the project automatically.

1. Choose a distribution license and add the corresponding `LICENSE` file.
2. Create an empty GitHub repository without generating a README, license, or `.gitignore`.
3. From the project folder, review and create the first commit:

   ```bash
   git status --short
   git add .
   git diff --cached --stat
   git commit -m "Initial commit"
   ```

4. Replace `YOUR_USERNAME` and configure the remote:

   ```bash
   git remote add origin git@github.com:YOUR_USERNAME/virtual_mouse.git
   git push -u origin main
   ```

The example uses SSH authentication. For HTTPS, copy the URL provided by GitHub.
Check the first run in the **Actions** tab.

The `.gitignore` excludes caches, virtual environments, credentials, and local
configuration. The `config.example.json` and `i3.conf.example` templates remain
available for publication.
