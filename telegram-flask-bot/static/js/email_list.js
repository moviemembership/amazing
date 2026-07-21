const body = document.body;
const deleteForm = document.getElementById("deleteForm");
const startDeleteButton =
    document.getElementById("startDeleteButton");
const cancelDeleteButton =
    document.getElementById("cancelDeleteButton");
const prepareDeleteButton =
    document.getElementById("prepareDeleteButton");

const noticeModal =
    document.getElementById("noticeModal");
const noticeTitle =
    document.getElementById("noticeTitle");
const noticeMessage =
    document.getElementById("noticeMessage");
const closeNoticeButton =
    document.getElementById("closeNoticeButton");

const confirmModal =
    document.getElementById("confirmModal");
const confirmDeleteMessage =
    document.getElementById("confirmDeleteMessage");
const cancelConfirmButton =
    document.getElementById("cancelConfirmButton");
const confirmDeleteButton =
    document.getElementById("confirmDeleteButton");

function selectedCheckboxes() {
    return Array.from(
        document.querySelectorAll(
            ".parent-checkbox:checked"
        )
    );
}

function clearSelections() {
    document.querySelectorAll(
        ".parent-checkbox"
    ).forEach(function (checkbox) {
        checkbox.checked = false;
    });
}

function showNoticeModal(title, message) {
    noticeTitle.textContent = title;
    noticeMessage.textContent = message;
    noticeModal.classList.add("show");
}

function closeNoticeModal() {
    noticeModal.classList.remove("show");
}

startDeleteButton.addEventListener(
    "click",
    function () {
        body.classList.add("delete-mode");
    }
);

cancelDeleteButton.addEventListener(
    "click",
    function () {
        clearSelections();
        body.classList.remove("delete-mode");
    }
);

prepareDeleteButton.addEventListener(
    "click",
    function () {
        const selected = selectedCheckboxes();

        if (selected.length === 0) {
            showNoticeModal(
                "Nothing selected",
                "Please select at least one parent email."
            );
            return;
        }

        confirmDeleteMessage.textContent =
            "Delete " +
            selected.length +
            " selected parent email(s)? " +
            "All replacement emails below them will also be deleted.";

        confirmModal.classList.add("show");
    }
);

closeNoticeButton.addEventListener(
    "click",
    closeNoticeModal
);

cancelConfirmButton.addEventListener(
    "click",
    function () {
        confirmModal.classList.remove("show");
    }
);

confirmDeleteButton.addEventListener(
    "click",
    function () {
        deleteForm.submit();
    }
);

noticeModal.addEventListener(
    "click",
    function (event) {
        if (event.target === noticeModal) {
            closeNoticeModal();
        }
    }
);

confirmModal.addEventListener(
    "click",
    function (event) {
        if (event.target === confirmModal) {
            confirmModal.classList.remove("show");
        }
    }
);

const noticeMessages = {
    none_selected: [
        "Nothing selected",
        "Please select at least one parent email."
    ],
    deleted: [
        "Deleted",
        "The selected parent accounts and their replacements were deleted."
    ],
    added: [
        "Emails added",
        "The parent email accounts were added successfully."
    ],
    replacement_added: [
        "Replacement added",
        "The replacement account was attached successfully."
    ],
    email_updated: [
    "Email updated",
    "The email account was updated successfully."
],
};

if (
    window.EMAIL_NOTICE &&
    noticeMessages[window.EMAIL_NOTICE]
) {
    window.addEventListener("load", function () {
        const message =
            noticeMessages[window.EMAIL_NOTICE];

        showNoticeModal(
            message[0],
            message[1]
        );
    });
}

document.querySelectorAll(
    ".copy-email-button"
).forEach(function (button) {

    button.addEventListener(
        "click",
        async function () {

            const copyType =
                button.dataset.copyType;

            const email =
                button.dataset.email;

            const password =
                button.dataset.password;

            const copyText =
                copyType +
                "\n\n" +
                email +
                "\n" +
                "password: " +
                password +
                "\n\n" +
                "Guide to login: " +
                "https://mantapnet.my/instructions" +
                "\n\n" +
                "Get code at " +
                "https://mantapnet.my/get-code";

            try {
                await navigator.clipboard.writeText(
                    copyText
                );

                const originalText =
                    button.textContent;

                button.textContent = "Copied";

                setTimeout(function () {
                    button.textContent =
                        originalText;
                }, 1200);

            } catch (error) {
                const textarea =
                    document.createElement("textarea");

                textarea.value = copyText;
                textarea.style.position = "fixed";
                textarea.style.opacity = "0";

                document.body.appendChild(
                    textarea
                );

                textarea.select();

                document.execCommand("copy");

                textarea.remove();

                const originalText =
                    button.textContent;

                button.textContent = "Copied";

                setTimeout(function () {
                    button.textContent =
                        originalText;
                }, 1200);
            }
        }
    );
});

const dateSections = document.querySelectorAll(
    ".email-date-group"
);

const dateButtons = document.querySelectorAll(
    ".date-jump-button"
);

if (
    dateSections.length > 0 &&
    dateButtons.length > 0
) {
    const dateObserver = new IntersectionObserver(
        function (entries) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) {
                    return;
                }

                dateButtons.forEach(function (button) {
                    button.classList.remove("active");
                });

                const activeButton =
                    document.querySelector(
                        '.date-jump-button[href="#' +
                        entry.target.id +
                        '"]'
                    );

                if (activeButton) {
                    activeButton.classList.add(
                        "active"
                    );

                    activeButton.scrollIntoView({
                        behavior: "smooth",
                        inline: "center",
                        block: "nearest"
                    });
                }
            });
        },
        {
            rootMargin: "-80px 0px -75% 0px",
            threshold: 0
        }
    );

    dateSections.forEach(function (section) {
        dateObserver.observe(section);
    });
}

const pageFindBar =
    document.getElementById("pageFindBar");

const pageFindInput =
    document.getElementById("pageFindInput");

const pageFindCount =
    document.getElementById("pageFindCount");

const pageFindPrevious =
    document.getElementById("pageFindPrevious");

const pageFindNext =
    document.getElementById("pageFindNext");

const pageFindClose =
    document.getElementById("pageFindClose");

const openPageFind =
    document.getElementById("openPageFind");

let pageFindMatches = [];
let pageFindCurrentIndex = -1;

function getEmailRows() {
    return Array.from(
        document.querySelectorAll(".email-row")
    );
}

function openFindBar() {
    if (!pageFindBar || !pageFindInput) {
        return;
    }

    pageFindBar.hidden = false;

    requestAnimationFrame(function () {
        pageFindInput.focus();
        pageFindInput.select();
    });
}

function clearFindState() {
    getEmailRows().forEach(function (row) {
        row.classList.remove(
            "find-hidden",
            "find-match",
            "find-current"
        );
    });

    pageFindMatches = [];
    pageFindCurrentIndex = -1;

    if (pageFindCount) {
        pageFindCount.textContent = "0 results";
    }
}

function closeFindBar() {
    if (!pageFindBar || !pageFindInput) {
        return;
    }

    pageFindBar.hidden = true;
    pageFindInput.value = "";
    clearFindState();
}

function updateCurrentMatch() {
    pageFindMatches.forEach(function (row, index) {
        row.classList.toggle(
            "find-current",
            index === pageFindCurrentIndex
        );
    });

    if (
        pageFindCurrentIndex >= 0 &&
        pageFindMatches[pageFindCurrentIndex]
    ) {
        pageFindMatches[
            pageFindCurrentIndex
        ].scrollIntoView({
            behavior: "smooth",
            block: "center"
        });
    }

    if (pageFindCount) {
        if (pageFindMatches.length === 0) {
            pageFindCount.textContent = "0 results";
        } else {
            pageFindCount.textContent =
                (pageFindCurrentIndex + 1) +
                " / " +
                pageFindMatches.length;
        }
    }
}

function runPageFind() {
    const query = pageFindInput
        ? pageFindInput.value.trim().toLowerCase()
        : "";

    const rows = getEmailRows();

    pageFindMatches = [];
    pageFindCurrentIndex = -1;

    rows.forEach(function (row) {
        row.classList.remove(
            "find-hidden",
            "find-match",
            "find-current"
        );

        if (!query) {
            return;
        }

        const rowText =
            row.textContent.toLowerCase();

        if (rowText.includes(query)) {
            row.classList.add("find-match");
            pageFindMatches.push(row);
        } else {
            row.classList.add("find-hidden");
        }
    });

    if (query && pageFindMatches.length > 0) {
        pageFindCurrentIndex = 0;
    }

    updateCurrentMatch();
}

function goToNextMatch() {
    if (pageFindMatches.length === 0) {
        return;
    }

    pageFindCurrentIndex =
        (pageFindCurrentIndex + 1) %
        pageFindMatches.length;

    updateCurrentMatch();
}

function goToPreviousMatch() {
    if (pageFindMatches.length === 0) {
        return;
    }

    pageFindCurrentIndex =
        (
            pageFindCurrentIndex -
            1 +
            pageFindMatches.length
        ) %
        pageFindMatches.length;

    updateCurrentMatch();
}

if (openPageFind) {
    openPageFind.addEventListener(
        "click",
        openFindBar
    );
}

if (pageFindInput) {
    pageFindInput.addEventListener(
        "input",
        runPageFind
    );

    pageFindInput.addEventListener(
        "keydown",
        function (event) {
            if (event.key === "Enter") {
                event.preventDefault();

                if (event.shiftKey) {
                    goToPreviousMatch();
                } else {
                    goToNextMatch();
                }
            }

            if (event.key === "Escape") {
                closeFindBar();
            }
        }
    );
}

if (pageFindNext) {
    pageFindNext.addEventListener(
        "click",
        goToNextMatch
    );
}

if (pageFindPrevious) {
    pageFindPrevious.addEventListener(
        "click",
        goToPreviousMatch
    );
}

if (pageFindClose) {
    pageFindClose.addEventListener(
        "click",
        closeFindBar
    );
}

document.addEventListener(
    "keydown",
    function (event) {
        const isFindShortcut =
            (event.ctrlKey || event.metaKey) &&
            event.key.toLowerCase() === "f";

        if (!isFindShortcut) {
            return;
        }

        event.preventDefault();
        openFindBar();
    }
);
