# Put your platform online for free: step by step

You do not need to install anything or write any code for Part A. You need a web browser
and about 20 minutes. Button names on the two websites may differ slightly from what is
written here; look for the closest match.

## Part A: get it online (no installs)

1. **Unzip the file.** Find `early_warning_v0_2.zip` in your Downloads and double-click it.
   You get a folder called `early_warning`. Open it. You should see `app.py`, `README.md`,
   and folders named `ew`, `cases`, `configs`, `tests` and `results`.

2. **Create a free GitHub account.** Go to https://github.com and sign up. GitHub is a
   website that stores project files. Remember your username.

3. **Create a repository** (a project folder on GitHub).
   - Click the **+** at the top right, then **New repository**.
   - Repository name: `early-warning`
   - Choose **Public**. (Free hosting in step 6 needs a public repository. Everything in it,
     including the evidence files, will be visible to anyone.)
   - Leave every tick-box empty and click **Create repository**.

4. **Upload the files.**
   - On the new, empty repository page, click the link **uploading an existing file**.
   - On your computer, open the `early_warning` folder, select **everything inside it**
     (Ctrl+A on Windows, Cmd+A on Mac) and drag it onto the GitHub page.
   - Important: drag the contents, not the `early_warning` folder itself. After the upload
     `app.py` must appear at the top level of the list.
   - Scroll down and click **Commit changes**.

5. **Create a free Streamlit account.** Go to https://share.streamlit.io and choose
   **Continue with GitHub**. Approve the access request. Streamlit is the service that
   turns `app.py` into a website.

6. **Deploy.**
   - Click **Create app** (or **New app**), then choose to deploy from GitHub.
   - Repository: `your-username/early-warning`
   - Branch: `main`
   - Main file path: `app.py`
   - Click **Deploy** and wait a few minutes while it installs.

7. **Open your platform.** Streamlit gives you a web address ending in `.streamlit.app`.
   That link works on any phone or computer. If nobody visits for a while the app goes to
   sleep; the next visitor clicks a wake-up button and waits a moment.

## Part B: use it and change it (still no installs)

8. **Explore.** In the left panel pick a case, a question and a date. The date is the
   important control: the app shows what the engine would have said using only what was
   public on that day.

9. **Add a piece of evidence.**
   - In the app open the **Add evidence** tab, fill in the form, click **Create record** and
     copy the line it gives you.
   - On GitHub open `cases`, then the case folder, then `evidence.json`. Click the pencil
     icon to edit.
   - Paste the line just before the final `]` at the bottom. Click **Commit changes**.
   - The website updates by itself within a minute or two.

10. **Start your own investigation.**
    - On GitHub, copy the `cases/nvidia_2026` folder's two files into a new folder, for
      example `cases/my_case/` (use **Add file**, then **Create new file**, and type
      `cases/my_case/case.json` as the name; paste the contents; repeat for `evidence.json`).
    - In `case.json` change the name, the focus, the links between people, and the questions
      with their starting values.
    - In `evidence.json` delete the old records and add your own with the form from step 9.
    - Write down your question and the starting value **before** you look for evidence.

11. **Keep score.** When a question's resolution date arrives, open the forecast log in
    `results`, set `"resolved"` to what happened, and never change the forecast itself.
    This is the only way to learn whether the platform works.

## Part C: run it on your own computer (optional, for later)

12. Install Python from https://www.python.org/downloads (on Windows tick **Add Python to
    PATH** during installation).
13. Open a terminal in the `early_warning` folder (Windows: type `cmd` in the folder's
    address bar; Mac: right-click the folder, **New Terminal at Folder**).
14. Type each line and press Enter:

```
pip install -r requirements.txt
streamlit run app.py
```

    The app opens in your browser. Two more useful commands:

```
python -m unittest discover -s tests    # checks nothing is broken
python run_all.py                       # re-runs every case and the tuning check
```

## What is free and what is not

| Piece | Cost | Limit to know about |
| --- | --- | --- |
| GitHub public repository | Free | Everything in it is public |
| Streamlit Community Cloud | Free for public apps | Goes to sleep when idle; modest memory |
| This engine | Free | Runs on plain Python, no paid services |
| Automatic news collection (GDELT, filings) | Free data | Needs code you have not built yet |
| Having an AI model read articles for you | Paid per use | Optional; manual entry is free |

Never put passwords, keys or private information in the repository.

## If something goes wrong

- **The app page shows an error about `app.py` not found:** the files were uploaded inside
  an extra folder. Delete the repository and repeat step 4, dragging the contents.
- **A red error after editing `evidence.json`:** a comma or bracket is misplaced. Every
  record ends with a comma except the last one, and the file ends with `]`. On GitHub click
  **History** on that file and revert the change.
- **"unknown signal type" or "entity is not reachable":** the record uses a name that is
  not in the catalog or the case's link list. Use the drop-downs in the form to avoid typos.


## Turn on the AI reader (free, about 5 minutes)

Without this the app reads headlines by keyword rules. With it, an AI model (Google Gemini, free tier)
works out what your question is about, checks whether the question is still valid, and picks out the
developments that matter.

1. Go to https://aistudio.google.com and sign in with a Google account.
2. Click **Get API key**, then **Create API key**. Copy the key (a long string of letters and numbers).
3. Open your app in the browser. Click **Manage app** (bottom right), then the three dots, then **Settings**, then **Secrets**.
4. Paste this one line, with your key between the quotes, and click **Save**:

       GEMINI_API_KEY = "paste-your-key-here"

5. The app restarts by itself. The line "Running in keyword mode" disappears from the Ask anything page.

Rules:
- **Never put the key in a file on GitHub.** Your repository is public; anyone could take the key. The Secrets box is private.
- The free tier has daily limits. If they are reached the app says so and falls back to keyword rules.
- On the free tier Google may use what is sent (your question and the headlines) to improve its products.
- Button names on Google's and Streamlit's sites may differ slightly from the ones above.


## Before a live demo

A live demo depends on three things that can fail: the app waking up, the news search, and the free AI service.

1. An hour before, open the site so it is awake, and ask the questions you plan to show.
2. Under each answer click **Save this full result**. Keep the files on the laptop you will present from.
3. If anything fails on stage, open **Advanced**, use **Show a saved result**, and pick the file. It shows the same answer
   with no internet or AI call.
4. Under the Why tab, **Check stability** reads the headlines a second time and tells you whether the two readings agree.

## Building a track record

Nothing here has been scored yet, and that is the first thing a careful audience will ask about.

1. Each time you ask a yes/no question, click **Download this forecast** and keep the file. Never edit it.
2. When the deadline passes, open the **Scorecard** page, load the files, and mark what happened.
3. The page shows the Brier score against two baselines (the starting values alone, and always saying 50%).
   Thirty or more settled forecasts are needed before the numbers mean anything.


## Your name and contact details on the site

Open `configs/site.json` and fill in `product_name`, `tagline`, `organisation`, `contact_name`, `contact_email`, and optionally
`video_url` (a YouTube or video link shown on the Home page). Leave a value empty to hide it. Then push. Everything in this file is
public, so only put details there that you want people to see.

## The system check (do this after every update)

Open the **Method** page and click **Run the system check**. It sends 13 difficult questions to the live AI model and checks that each
is understood correctly: negative questions, "still" questions, typos, far-off elections, and questions it should refuse. If any row
says FAIL, send a screenshot of the table. This is the test that cannot be run anywhere except on the live site.
