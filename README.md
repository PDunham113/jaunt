# jaunt

It's just a really barebones management utility for MySQL migrations. Not much else to
say, really.

## Why make another migration tool?

Not too complicated, really:

1.  **I HATE the idea of having SQL database migrations not written in SQL.**
    It's a shockingly functional language, and I actually find it (especially DDL)
    noticeably more readable wrt database construction and manipulation than python or
    JS. Something something right tool for the job.
2.  **I don't like the idea of installing a whole other toolchain for a migration tool**
    i.e. install node just to use knex, or all of Django just to use its migration
    schema. Having to lift Python into place for this tool is still not perfect - but
    everyone and their mother has some Python install for whatever reason, and it's
    either this or compiled binaries. At least this uses stdlib wherever possible.
3.  **I'm a control freak**
    I won't pretend I'm not lol. I feel safer knowing exactly what's going on, even
    though I'm SURE that the vast majority of tools like this out there are
    better-designed, more functional, and well-tested. In addition, it's a good learning
    experience!

## Why should I use this one?

Don't.

Really, don't. If you have data in a database that you care about, look elsewhere. There
are a lot of great migration tools out there - Flyway is the closest to what I wanted
(it supports pure-SQL migrations and seems otherwise fairly sensible), and I've had good
experiences with the migration utilities built into knex and Django.

I can and will change how this tool works to my liking until, well, I like it - at that
point, I'll probably care about versioning. Until then, this can and will break at a
moment's notice.

If that doesn't scare you away, the goals of this tool are fairly straightforward:
* Be absurdly simple to set up
* Be absurdly simple to understand
* Define migrations in native SQL
* Do as little as possible other than applying migrations

## Why is it called jaunt?

Because `flock` is already a command-line utility. I'm mad about it, that would've been
way cooler.

## Setting this up

Get some version of Python 3 (best chance being 3.10+), and the Python MySQL connector.
Then go to town - it should work out of the box.
