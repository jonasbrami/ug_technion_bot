import mechanicalsoup
import time
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters,
                              ConversationHandler)


# SECURITY CONSTANTS

BOT_TOKEN = 'ENTER YOUR TOKEN HERE'
ADMIN_USERNAME = 'enter your username'

# To notify the users before a bot update/restart
chats_id_list = list()

# constants used to wait between requests on the webserver to avoid being banned/blacklisted
TIME_BETWEEN_REQUESTS = 30
TIME_BETWEEN_POOLS = 300
TIME_BETWEEN_RETRY = 3
MAX_NUMBER_OF_RETRY = 5

# Telegram BOT states
IDS, COURSES, AUTOMATIC, POOL = range(4)

# Logging features
current_number_of_job = 0
total_number_of_jobs_created = 0

# Web server helper functions
def ug_login(id, pwd):
    """

    :param id: user's UG id
    :param pwd: user's UG password
    :return: A logged browser if the id's are correct and UG is up. Else, a browser on the login or no service page.
    """
    browser = mechanicalsoup.StatefulBrowser()
    for i in range(MAX_NUMBER_OF_RETRY):
        try:
            browser.open("https://ug3.technion.ac.il/rishum/login")
            if browser.get_url() == 'https://ug3.technion.ac.il/rishum/no-service':
                return browser
            browser.select_form()
            browser.get_current_form()
            browser["UID"] = id
            browser["PWD"] = pwd
            browser.submit_selected()
        except Exception: #sometimes, the webserver times out...
            pass
        if browser.get_url() == 'https://ug3.technion.ac.il/rishum/cart':
            break
        time.sleep(TIME_BETWEEN_RETRY)
    return browser


def checker(courses, id, pwd):
    """

    :param courses: A list of valid courses
    :param id: user's UG id
    :param pwd: user's UG password
    :return: A list of courses where a spot is available
    """

    available_list = list()
    browser = ug_login(id, pwd)
    if browser.get_url() == 'https://ug3.technion.ac.il/rishum/no-service':
        return list()

    if browser.get_url() != 'https://ug3.technion.ac.il/rishum/cart':
        raise Exception("Wrong IDs")

    for course in courses:
        browser.open('https://ug3.technion.ac.il/rishum/vacancy/' + course)
        page = browser.get_current_page()
        course_is_available = not bool(page.find("div", class_="error-msg"))
        if course_is_available:
            available_list.append(course)
        time.sleep(TIME_BETWEEN_REQUESTS)
    return available_list


def is_valid_course(course):
    """

    :param course
    :return: True iff course exists
    """

    if len(course) > 6:
        return False
    browser = mechanicalsoup.StatefulBrowser()
    browser.open('https://ug3.technion.ac.il/rishum/search')
    browser.select_form()
    browser['CNO'] = course
    browser.submit_selected()
    return bool(browser.get_current_page().find("div", class_="course-number"))


def try_to_register(bot, chat_data, available_list):
    browser = ug_login(chat_data['id'], chat_data['password'])
    if browser.get_url() == 'https://ug3.technion.ac.il/rishum/no-service':
        return
    for course in available_list:
        browser.open('https://ug3.technion.ac.il/rishum/vacancy/' + course)
        browser.follow_link(link=browser.links(link_text="הוסף לסל")[0])
        browser.open("https://ug3.technion.ac.il/rishum/register/confirm")
        if browser.links(url_regex='https://ug3.technion.ac.il/rishum/register/remove/' + course):
            bot.send_message(chat_id=chat_data['chat_id'], text=course + ' successfully added')
        else:
            bot.send_message(chat_id=chat_data['chat_id'], text=course + ' NOT successfully added. Register manually!')
        time.sleep(TIME_BETWEEN_REQUESTS)


# Telegram BOT job callbacks

def pool(bot, job):
    """

    :param chat_data : Passed through job.context.
    Pool the webserver for free spots and update the user accordingly
    """
    chat_data = job.context
    notification = ""
    if len(chat_data['courses']) == 0:
        chat_data['job'].enabled = False
        bot.send_message(chat_id=chat_data['chat_id'],
                         text="No more course to pool. Job disabled"+'\n'
                              " send /cancel and then /start to create a new one.")
        return
    try:
        available_list = checker(chat_data['courses'], chat_data['id'], chat_data['password'])
    except Exception:
        chat_data['job'].enabled = False
        bot.send_message(chat_id=chat_data['chat_id'],
                         text="Wrong IDs, Job disabled, send /cancel and then /start to create a new one.")
        return

    for course in available_list:
        notification += "A spot is available for " + course + "\n"
        chat_data['courses'].remove(course)

    if notification != "":
        bot.send_message(chat_id=chat_data['chat_id'], text=notification)

    if chat_data['automatic'] == True:
        try_to_register(bot, chat_data, available_list)


# Telegram BOT states and fallbacks callbacks

def start(bot, update):
    global chats_id_list
    chats_id_list.append(update.message.chat_id)
    update.message.reply_text("Enter your ug's id and password separated by one space. Example:\n123456789 password")
    return IDS


def get_ids(bot, update, chat_data):
    if len(update.message.text.split()) != 2:
        update.message.reply_text("Wrong number of argument, try again")
        return IDS
    chat_data['id'], chat_data['password'] = update.message.text.split()
    chat_data['chat_id'] = update.message.chat_id
    update.message.reply_text("Enter the course's number. Example:\n11111 22222")
    return COURSES


def get_courses(bot, update, chat_data):
    chat_data['courses'] = list()

    for course in update.message.text.split():
        if is_valid_course(course):
            chat_data['courses'].append(course)
        else:
            update.message.reply_text("The course " + course + " isn't a valid course")

    update.message.reply_text("Do you want the bot to automatically register when an available spot is found ?" + '\n' +
                              "Send yes to enable it or anything else to disable it")
    return AUTOMATIC


def activate_auto_and_schedule_job(bot, update, chat_data, job_queue):
    if update.message.text == 'yes':
        chat_data['automatic'] = True
        update.message.reply_text('Automatic mode enabled')
    else:
        chat_data['automatic'] = False
        update.message.reply_text('Automatic mode disabled')

    update.message.reply_text("You will receive a notification as soon as a spot is available" + '\n' +
                              "Pooling started! Send /cancel to stop the job or anything else to get the status")
    job = job_queue.run_repeating(pool, interval=TIME_BETWEEN_POOLS, first=0, context=chat_data)
    chat_data['job'] = job

    global current_number_of_job
    global total_number_of_jobs_created
    current_number_of_job += 1
    total_number_of_jobs_created += 1

    return POOL


def job_already_running(bot, update, chat_data):

    if not chat_data['job'].enabled :
        update.message.reply_text("No job running. Send /start to make a new one")

        global current_number_of_job
        current_number_of_job += 1

        return ConversationHandler.END

    update.message.reply_text(
        "******** STATUS *********" + '\n'
        "A job is already running for "
        + ' '.join(chat_data['courses']) + '\n'
        + 'Automatic mode is ' + str(chat_data['automatic']) + '\n'
        + "To modify the job, send /cancel to stop it and then /start to make a new one" + '\n' + '\n'
        + "current number of jobs in the system : " + str(current_number_of_job) + '\n'
        + "total number of jobs created : " + str(total_number_of_jobs_created))
    return POOL


def cancel(bot, update, chat_data):
    chat_data['job'].schedule_removal()
    update.message.reply_text("Pooling Stopped! Send /start to create a new job")

    global current_number_of_job
    current_number_of_job += 1
    return ConversationHandler.END


def notify_users(bot,update):
    if update.message.from_user.username != ADMIN_USERNAME:
        update.message.reply_text("unauthorized username!")
        return
    for chat_id in chats_id_list:
        bot.send_message(chat_id=chat_id, text="The BOT is about to restart, you'll need to restart a new job")

###


updater = Updater(token=BOT_TOKEN)

dispatcher = updater.dispatcher

ug_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={

        IDS: [MessageHandler(Filters.text, get_ids, pass_chat_data=True)],

        COURSES: [MessageHandler(Filters.text, get_courses, pass_chat_data=True)],

        AUTOMATIC: [MessageHandler(Filters.text, activate_auto_and_schedule_job, pass_chat_data=True, pass_job_queue=True)],

        POOL: [MessageHandler(Filters.text, job_already_running, pass_chat_data=True)],
    },
    fallbacks=[CommandHandler('cancel', cancel, pass_chat_data=True)]
)

admin_handler = CommandHandler('admin', notify_users)
dispatcher.add_handler(ug_handler)
dispatcher.add_handler(admin_handler)
updater.start_polling()
